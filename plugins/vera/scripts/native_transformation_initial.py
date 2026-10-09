"""Create only exact host-bound synthetic stores through the public producer.

Empty-directory checks, byte identities, draft CAS and durable intents implement
mechanical ownership and recovery; they never select law or infer case facts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_transformation import bindings, bounded, files, read, regular, stamp

__all__ = ["dispatch", "initial_option"]
PREFIX = "vera_workspace_transformation_initial_"
EMPTY = {"owner": "", "purpose": ""}


def fields_check(value: Any) -> None:
    """Retain literal incomplete fields without generating professional facts."""
    if (
        not isinstance(value, dict)
        or set(value) != set(EMPTY)
        or any(not isinstance(v, str) or len(v) > 4000 for v in value.values())
    ):
        raise ValueError("Invalid literal synthetic initialization fields")


def paths(owner: dict, row: dict) -> tuple[Path, Path]:
    """Bind the new public target separately from pre-existing private controls."""
    if row.get("initialize") is not True or row.get("synthetic_only") is not True:
        raise PermissionError("Host must explicitly bind synthetic initialization")
    if row.get("sources", []) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,120}", row["case_id"]
    ):
        raise ValueError(
            "Initialize without sources; bind synthetic inputs after creation"
        )
    selected = []
    for key in ("case_dir", "initial_state_dir"):
        path = Path(row[key])
        regular(path)
        resolved = path.resolve()
        if (
            not path.is_absolute()
            or any((p / ".git").exists() for p in (resolved, *resolved.parents))
            or {"public", "published", "static", "plugin_packages", "engagements"}
            & {p.lower() for p in resolved.parts}
            or resolved in {Path(resolved.anchor), Path.home().resolve()}
        ):
            raise ValueError(
                "Use dedicated synthetic directories outside Git and client engagements"
            )
        selected.append(resolved)
    root, controls = selected
    if (
        not root.parent.is_dir()
        or not controls.is_dir()
        or root.is_relative_to(controls)
        or controls.is_relative_to(root)
    ):
        raise ValueError(
            "Separate the empty synthetic target from existing private controls"
        )
    if root.exists() and not root.is_dir():
        raise ValueError("Synthetic target must be a new or empty directory")
    private = controls / (
        "transformation-initial-" + stamp({"owner": owner, "binding": row})
    )
    regular(private)
    private.mkdir(mode=0o700, exist_ok=True)
    return root, private


def producer(module: Path, root: Path, row: dict, action: str, **args: Any) -> dict:
    """Run the unchanged public initialization or load helper in isolation."""
    request = {
        "module": str(module),
        "root": str(root),
        "case_id": row["case_id"],
        "action": action,
        **args,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_transformation_initial_bridge.py")),
        ],
        input=bounded(request),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            "Synthetic initialization producer failed; retain intent and recover through the specialist workflow"
        )
    data = json.loads(result.stdout)
    bounded(data)
    return data


def state_read(private: Path) -> tuple[dict, dict]:
    """Verify private drafts and receipts before exposing a resumable stage."""
    draft = (
        read(private / "draft.json")
        if (private / "draft.json").is_file()
        else {"generation": 0, "revision": "", "fields": dict(EMPTY)}
    )
    fields_check(draft["fields"])
    intents = (
        read(private / "operations.json")
        if (private / "operations.json").is_file()
        else {}
    )
    for key, item in intents.items():
        if (
            item["status"] not in {"pending", "completed"}
            or stamp(item["request"]) != item["fingerprint"]
            or item["request"]["idempotency_key"] != key
        ):
            raise ValueError("Synthetic initialization intent integrity mismatch")
        if (
            item["status"] == "completed"
            and stamp(item["result"]) != item["receipt_sha256"]
        ):
            raise ValueError("Synthetic initialization receipt integrity mismatch")
    return draft, intents


def snapshot(
    owner: dict, row: dict, module: Path
) -> tuple[Path, Path, dict, dict, dict]:
    """Show exact new/created state while preserving all unknown public attributes."""
    root, private = paths(owner, row)
    before = files(root) if root.exists() else {}
    draft, intents = state_read(private)
    pending = [key for key, item in intents.items() if item["status"] == "pending"]
    created = (root / "history").is_dir()
    state = producer(module, root, row, "inspect") if created else None
    if not created and root.exists() and any(root.iterdir()):
        raise ValueError("Synthetic initialization target is not empty")
    if before != (files(root) if root.exists() else {}):
        raise ValueError("Synthetic initialization target changed during inspection")
    implementation = {
        "public/" + key: value
        for key, value in files(module / "scripts").items()
        if key.endswith(".py")
    }
    for path in (
        Path(__file__),
        Path(__file__).with_name("native_transformation_initial_bridge.py"),
        Path(__file__).parents[1] / "ui/transformation.js",
    ):
        regular(path)
        implementation[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    revision = stamp(
        {
            "owner": owner,
            "binding": row,
            "files": before,
            "implementation": implementation,
        }
    )
    page = {
        "work_ref": row["work_ref"],
        "revision": revision,
        "source_ref": revision,
        "fields": draft["fields"],
        "draft_revision": stamp(draft),
        "draft_stale": bool(draft["revision"] and draft["revision"] != revision),
        "pending_operations": pending,
        "created": created,
        "can_write": not created
        and not pending
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
        "confirmation_restored": False,
        "synthetic_only": True,
        "professional_validation": False,
        "model_context_transferred": False,
        "data": {
            "selection": {"source_ref": revision},
            "case_id": row["case_id"],
            "state": state,
        },
    }
    return root, private, page, draft, intents


def initial_option(owner: dict, row: dict, module: Path) -> dict | None:
    """Keep uncertain creation visible instead of exposing an editable existing case."""
    if row.get("initialize") is not True:
        return None
    _, _, page, _, _ = snapshot(owner, row, module)
    if page["created"] and not page["pending_operations"]:
        return None
    return {
        "work_ref": row["work_ref"],
        "case_id": row["case_id"],
        "objective": (
            "Nuovo prototipo sintetico"
            if not page["created"]
            else "Creazione incerta · recupero richiesto"
        ),
        "case_revision": 0,
        "synthetic_only": True,
        "initialization": True,
    }


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    """Preserve drafts and explicit synthetic consent before one public creation."""
    owner, rows = bindings()
    row = next((r for r in rows if r["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned synthetic initialization")
    root, private = paths(owner, row)
    action = tool.removeprefix(PREFIX)
    with api.write_lock(private / "initialization"):
        _, _, page, current, intents = snapshot(owner, row, module)
        if action == "setup":
            return page
        if "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","):
            raise PermissionError(
                "Synthetic initialization requires reviewer authority"
            )
        if action == "create" and args["idempotency_key"] in intents:
            prior = intents[args["idempotency_key"]]
            if stamp(args) != prior["fingerprint"]:
                raise ValueError("Changed synthetic initialization retry")
            if prior["status"] != "completed":
                raise ValueError(
                    "Uncertain synthetic initialization requires specialist recovery"
                )
            if page["revision"] != prior["after_revision"]:
                raise ValueError("Synthetic case changed after initialization")
            return prior["result"]
        if page["created"] or page["pending_operations"]:
            raise ValueError(
                "Resume the created case or recover uncertain creation; never initialize again"
            )
        if any(args[key] != page[key] for key in ("revision", "source_ref")) or args[
            "expected_draft_revision"
        ] != stamp(current):
            raise ValueError(
                "Synthetic initialization or private fields changed; reopen the stage"
            )
        if action in {"draft_save", "draft_clear"}:
            if action == "draft_clear" and args.get("confirmed") is not True:
                raise ValueError(
                    "Confirm discarding only private initialization fields"
                )
            fields = dict(EMPTY) if action == "draft_clear" else args["fields"]
            fields_check(fields)
            updated = {
                "generation": current["generation"] + 1,
                "revision": "" if action == "draft_clear" else page["revision"],
                "fields": fields,
            }
            api.atomic_json(private / "draft.json", updated)
            return {
                "saved": True,
                "draft_revision": stamp(updated),
                "confirmation_restored": False,
            }
        if action != "create":
            raise ValueError("Unknown synthetic initialization action")
        fields = args["fields"]
        fields_check(fields)
        if (
            fields != current["fields"]
            or current["revision"] != page["revision"]
            or args.get("confirmed") is not True
            or args.get("synthetic_only") is not True
            or not all(v.strip() for v in fields.values())
        ):
            raise ValueError(
                "Save owner and purpose, then explicitly confirm a synthetic case only"
            )
        key = args["idempotency_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", key):
            raise ValueError("Invalid synthetic initialization key")
        intent = {"status": "pending", "request": args, "fingerprint": stamp(args)}
        intents[key] = intent
        api.atomic_json(private / "operations.json", intents)
        state = producer(
            module, root, row, "initialize", fields=fields, expected_files={}
        )
        _, _, after, _, _ = snapshot(owner, row, module)
        receipt = {
            "created": True,
            "work_ref": row["work_ref"],
            "case_id": state["case"]["id"],
            "case_revision": state["revision"],
            "synthetic_only": True,
            "professional_validation": False,
            "sent_or_published": False,
        }
        intent.update(
            status="completed",
            result=receipt,
            receipt_sha256=stamp(receipt),
            after_revision=after["revision"],
        )
        api.atomic_json(private / "operations.json", intents)
        return receipt
