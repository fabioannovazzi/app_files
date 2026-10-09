"""Selective browser-process progress and exact operator batch-review panel.

Receipts, hash checks and CAS serve fixed integrity contracts, never page meaning.
Browser execution, model-led recovery and professional accounting stay unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_transformation import bounded, files, read, regular, stamp

__all__ = ["dispatch"]
PREFIX = "vera_workspace_browser_"
EMPTY = {"decision": "", "note": ""}


def fields(value: Any) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != set(EMPTY)
        or any(not isinstance(v, str) or len(v) > 4000 for v in value.values())
        or value["decision"] not in {"", "checked", "correction_requested"}
    ):
        raise ValueError("Invalid browser-review fields")
    return dict(value)


def configuration() -> tuple[dict, list]:
    owner = {
        key: os.environ.get("VERA_WORKSPACE_" + key.upper(), "")
        for key in ("tenant_id", "actor_id")
    }
    if not all(owner.values()):
        raise PermissionError("Open browser reviews through the owned MCP service")
    location = os.environ.get("VERA_BROWSER_WORKSPACE_BINDINGS")
    if not location:
        return owner, []
    payload = read(Path(location))
    if any(payload.get(k) != v for k, v in owner.items()):
        raise PermissionError("Browser review belongs to another operator")
    rows = payload["bindings"]
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("Bind at most 200 exact browser reviews")
    refs = [r["work_ref"] for r in rows]
    if len(set(refs)) != len(refs) or any(
        not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", v)
        for v in refs
    ):
        raise ValueError("Use unique browser review references")
    return owner, rows


def connection(row: dict) -> Path:
    root = Path(row["directory"])
    regular(root)
    if (
        not root.is_absolute()
        or not root.is_dir()
        or root in {Path(root.anchor), Path.home()}
        or any((p / ".git").exists() for p in (root, *root.parents))
        or {"static", "public", "published", "plugin_packages"}
        & {p.lower() for p in root.parts}
    ):
        raise ValueError(
            "Bind one exact private existing browser record outside Git and public folders"
        )
    if row["kind"] not in {"process", "batch"}:
        raise ValueError("Select a public process register or saved batch review")
    if row["kind"] == "process" and not re.fullmatch(
        r"process-[a-f0-9]{32}", row["process_id"]
    ):
        raise ValueError("Select an exact registered process identity")
    if row["kind"] == "batch":
        regular(Path(row["client_root"]))
        if not Path(row["client_root"]).is_absolute():
            raise ValueError("Declare the exact client Archive")
    return root


def producer(module: Path, row: dict, action: str, **args: Any) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_browser_bridge.py")),
        ],
        input=bounded(
            {"module": str(module), "binding": row, "action": action, **args}
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if completed.returncode:
        raise ValueError(
            "Browser review producer refused this operation; inspect its exact identity, evidence and public recovery workflow"
        )
    value = json.loads(completed.stdout)
    bounded(value)
    return value


def snapshot(owner: dict, row: dict, module: Path) -> tuple[Path, dict]:
    root = connection(row)
    before = files(root)
    data = producer(module, row, "snapshot")
    implementation = {
        name: value
        for name, value in files(module).items()
        if Path(name).suffix in {".py", ".mjs", ".cjs", ".json", ".md", ".svg"}
    }
    for path in (
        Path(__file__),
        Path(__file__).with_name("native_browser_bridge.py"),
        Path(__file__).parents[1] / "ui/browser.js",
    ):
        regular(path)
        implementation[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    implementation.update(data["shared_implementation"])
    if files(root) != before:
        raise ValueError("Browser records changed during readback")
    revision = stamp([owner, row, before, implementation, data])
    return root, {
        "work_ref": row["work_ref"],
        "kind": row["kind"],
        "revision": revision,
        "source_ref": revision,
        "data": {"selection": {"source_ref": revision}, **data},
    }


def receipt(path: Path) -> dict:
    value = read(path)
    if value["content_sha256"] != stamp(
        {k: v for k, v in value.items() if k != "content_sha256"}
    ):
        raise ValueError("Browser review receipt changed")
    return value


def seal(path: Path, value: dict, api: Any) -> None:
    api.atomic_json(path, {**value, "content_sha256": stamp(value)})


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    owner, rows = configuration()
    action = tool.removeprefix(PREFIX)
    if action == "catalogue":
        works = []
        for row in rows:
            _, page = snapshot(owner, row, module)
            data = page["data"]
            works.append(
                {
                    "work_ref": row["work_ref"],
                    "kind": row["kind"],
                    "title": (
                        data["record"]["payload"]["title"]
                        if row["kind"] == "batch"
                        else data["process"]["description"]["process"]["name"]
                    ),
                }
            )
        return {
            "configured": bool(rows),
            "works": works,
            "model_context_transferred": False,
        }
    row = next((r for r in rows if r["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned browser review")
    root = connection(row)
    with api.write_lock(root / "native-browser-marker"):
        _, page = snapshot(owner, row, module)
        if action == "setup":
            return page
        if action == "artifact":
            if row["kind"] != "batch" or any(
                args[k] != page[k] for k in ("revision", "source_ref")
            ):
                raise PermissionError("Select a current batch artifact")
            target = root / page["data"]["artifact"]["name"]
            regular(target)
            content = target.read_bytes()
            if (
                len(content) > 1_000_000
                or hashlib.sha256(content).hexdigest()
                != page["data"]["artifact"]["sha256"]
            ):
                raise ValueError(
                    "Complete verified report changed or exceeds native download limit"
                )
            return {
                "name": target.name,
                "base64": base64.b64encode(content).decode(),
                "mime_type": "application/octet-stream",
            }
        if row["kind"] != "batch":
            raise PermissionError(
                "Process progress is read only; use the ordinary browser workflow"
            )
        entry = next(
            (
                r
                for r in page["data"]["record"]["payload"]["entries"]
                if r["id"] == args["item_id"]
            ),
            None,
        )
        if entry is None:
            raise PermissionError("Select an exact current batch entry")
        source_ref = stamp(entry)
        page.update(source_ref=source_ref, selection={"id": entry["id"]})
        page["data"]["selection"] = {"source_ref": source_ref}
        directory = (
            root / ".native-workspace" / ("browser-" + stamp([owner, row, entry["id"]]))
        )
        regular(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / "draft.json"
        draft = (
            read(path)
            if path.exists()
            else {"generation": 0, "revision": "", "fields": dict(EMPTY)}
        )
        fields(draft["fields"])
        intents = {p.name: receipt(p) for p in sorted(directory.glob("intent-*.json"))}
        pending = [key for key, value in intents.items() if "result" not in value]
        editable = "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        if action == "read":
            return {
                **page,
                "entry": entry,
                "fields": draft["fields"],
                "draft_revision": stamp(draft),
                "draft_stale": bool(
                    draft["revision"] and draft["revision"] != page["revision"]
                ),
                "can_write": editable,
                "pending_operations": pending,
                "confirmation_restored": False,
            }
        if not editable:
            raise PermissionError("Operator review authority required")
        if action == "review_commit":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", args["idempotency_key"]):
                raise ValueError("Invalid browser-review key")
            intent = directory / ("intent-" + stamp(args["idempotency_key"]) + ".json")
            if intent.exists():
                prior = receipt(intent)
                if prior["request_sha256"] != stamp(args):
                    raise ValueError(
                        "Browser-review key belongs to another exact request"
                    )
                if "result" not in prior:
                    raise ValueError(
                        "Browser-review write uncertain; recover through the public workflow"
                    )
                if prior["after_revision"] != page["revision"]:
                    raise ValueError("Batch advanced since the completed receipt")
                return prior["result"]
        if any(args[k] != page[k] for k in ("revision", "source_ref")) or args[
            "expected_draft_revision"
        ] != stamp(draft):
            raise ValueError("Browser review scope or draft CAS changed")
        if action == "draft_clear":
            if args["confirmed"] is not True:
                raise ValueError("Confirm private draft discard")
            value = {
                "generation": draft["generation"] + 1,
                "revision": page["revision"],
                "fields": dict(EMPTY),
            }
            api.atomic_json(path, value)
            return {
                "saved": True,
                "draft_revision": stamp(value),
                "fields": value["fields"],
            }
        selected = fields(args["fields"])
        if draft["revision"] and draft["revision"] != page["revision"]:
            raise ValueError("Compare and explicitly discard stale private fields")
        if action == "draft_save":
            value = {
                "generation": draft["generation"] + 1,
                "revision": page["revision"],
                "fields": selected,
            }
            api.atomic_json(path, value)
            return {"saved": True, "draft_revision": stamp(value), "fields": selected}
        if (
            action != "review_commit"
            or pending
            or selected != draft["fields"]
            or args["confirmed"] is not True
            or not selected["decision"]
            or not selected["note"].strip()
        ):
            raise ValueError(
                "Save the actual explicit review and renew confirmation; recover uncertain writes first"
            )
        seal(intent, {"owner": owner, "request_sha256": stamp(args)}, api)
        result = producer(
            module,
            row,
            "record_review",
            expected_files=files(root),
            item_id=entry["id"],
            fields=selected,
        )
        _, after = snapshot(owner, row, module)
        if result["record"] != after["data"]["record"]:
            raise ValueError(
                "Conserved browser review changed; recover retained intent"
            )
        summary = {
            "saved": True,
            "work_ref": page["work_ref"],
            "revision": after["revision"],
            "record": result["record"],
            "browser_executed": False,
            "accounting_correction_executed": False,
            "archive_changed": False,
            "authenticated_signature": False,
        }
        seal(
            intent,
            {
                "owner": owner,
                "request_sha256": stamp(args),
                "after_revision": after["revision"],
                "result": summary,
            },
            api,
        )
        return json.loads(bounded(summary))
