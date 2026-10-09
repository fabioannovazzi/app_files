"""Owner-scoped native review over a separate studio-wide communications store.

Fixed path, byte, CAS and receipt checks protect auditability. They do not choose
topics, assess claims, infer approval, dispatch model sessions or publish content.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["dispatch"]

LIMIT = 2_000_000
PREFIX = "vera_workspace_communication_"
ACTIONS = {
    "semantic_review",
    "render_review",
    "package_review",
    "qa_preview",
    "render",
    "package",
    "validate",
    "promote_profile",
}


def bounded(value: Any) -> str:
    """Refuse an oversized whole record, never sample a review population."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(raw.encode()) > LIMIT:
        raise ValueError("Complete communication payload exceeds native limit")
    return raw


def stamp(value: Any) -> str:
    """Exact byte identities make stale proposals and changed retries observable."""
    return hashlib.sha256(bounded(value).encode()).hexdigest()


def regular(path: Path) -> None:
    """Reject linked paths before any read or write outside the bound workspace."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Communication paths cannot use symbolic links")
    if (
        path.exists()
        and not path.is_dir()
        and (not path.is_file() or path.stat().st_nlink != 1)
    ):
        raise ValueError("Communication files must be regular and single-link")


def read(path: Path) -> dict:
    regular(path)
    if path.stat().st_size > LIMIT:
        raise ValueError("Communication record exceeds whole-record limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Communication record must be an object")
    return value


def files(root: Path) -> dict:
    """Hash every retained studio file, excluding only native interaction state."""
    regular(root)
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == ".native-workspace":
            continue
        regular(path)
        # The maintained writer updates its PID/time even on a locked read.
        # Preserve path/link checks but exclude only those two fixed lock locations.
        public_lock = relative.name == ".comunicazione-professionale.lock" and (
            len(relative.parts) == 1
            or (len(relative.parts) == 3 and relative.parts[0] == "runs")
        )
        if path.is_file() and not public_lock:
            with path.open("rb") as stream:
                result[relative.as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    bounded(result)
    return result


def bindings() -> tuple[dict, list]:
    """Only a trusted host binding selects exact existing studio-wide runs."""
    owner = {
        key: os.environ.get("VERA_WORKSPACE_" + key.upper(), "")
        for key in ("tenant_id", "actor_id")
    }
    if not all(owner.values()):
        raise PermissionError("Open communications through its owned local MCP service")
    filename = os.environ.get("VERA_COMMUNICATION_WORKSPACE_BINDINGS")
    if not filename:
        return owner, []
    config = read(Path(filename))
    if any(config.get(key) != value for key, value in owner.items()):
        raise PermissionError("Communications binding belongs to another host actor")
    rows = config["bindings"]
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("Communications binding supports at most 200 exact runs")
    refs = [row["work_ref"] for row in rows]
    if len(set(refs)) != len(refs) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", ref) for ref in refs
    ):
        raise ValueError("Communication references must be unique bounded identifiers")
    return owner, rows


def connection(row: dict, module: Path) -> tuple[Path, Path]:
    """Keep the maintained studio-wide store outside Git and client engagements."""
    workspace = Path(row["workspace"])
    regular(workspace)
    workspace = workspace.resolve()
    repository = module.resolve().parents[1]
    if workspace.is_relative_to(repository) or {
        "public",
        "published",
        "static",
        "plugin_packages",
        "engagements",
    } & {p.lower() for p in workspace.parts}:
        raise ValueError(
            "Use a private studio-wide communication workspace outside client engagements"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}", row["run_id"]):
        raise ValueError("Invalid communication run ID")
    manifest = read(workspace / "workspace.json")
    if (
        manifest["workflow"] != "comunicazione-professionale"
        or Path(manifest["bound_path"]).resolve() != workspace
        or manifest["workspace_id"] != row["workspace_id"]
    ):
        raise PermissionError("Communication workspace binding changed")
    run = workspace / "runs" / row["run_id"]
    regular(run)
    if not run.is_dir():
        raise ValueError("The selected communication run does not exist")
    return workspace, run


def producer(
    module: Path, workspace: Path, row: dict, action: str, **arguments: Any
) -> dict:
    """Run only fixed maintained public helpers in an isolated Python process."""
    request = {
        "module": str(module),
        "workspace": str(workspace),
        "run_id": row["run_id"],
        "action": action,
        **arguments,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_communication_bridge.py")),
        ],
        input=bounded(request),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1]
            if result.stderr.strip()
            else "Communication producer failed"
        )
    value = json.loads(result.stdout)
    bounded(value)
    return value


def snapshot(owner: dict, row: dict, module: Path) -> tuple[Path, Path, dict]:
    """Replay the public contribution contract and every current retained byte."""
    workspace, run = connection(row, module)
    before = files(workspace)
    data = producer(module, workspace, row, "snapshot")
    if data["run_id"] != row["run_id"] or data["workbench"]["run_id"] != row["run_id"]:
        raise PermissionError("Communication run binding changed")
    if before != files(workspace):
        raise ValueError("Communication changed during native inspection")
    implementation = {
        section + "/" + key: value
        for section in ("scripts", "schemas", "prompts", "skills")
        for key, value in files(module / section).items()
        if Path(key).suffix in {".py", ".json", ".md"}
    }
    for name in ("native_communication.py", "native_communication_bridge.py"):
        implementation[name] = hashlib.sha256(
            Path(__file__).with_name(name).read_bytes()
        ).hexdigest()
    implementation["communication-ui"] = hashlib.sha256(
        Path(__file__).parents[1].joinpath("ui/communication.js").read_bytes()
    ).hexdigest()
    revision = stamp(
        {
            "owner": owner,
            "binding": row,
            "files": before,
            "implementation": implementation,
        }
    )
    return (
        workspace,
        run,
        {
            "work_ref": row["work_ref"],
            "revision": revision,
            "source_ref": revision,
            "data": {"selection": {"source_ref": revision}, **data},
        },
    )


def draft(directory: Path) -> dict:
    """Retain literal choices without professional consent or a public decision."""
    path = directory / "draft.json"
    return (
        read(path)
        if path.is_file()
        else {
            "generation": 0,
            "revision": "",
            "fields": {
                "operation": "",
                "reviewer": "",
                "decisions": {},
                "decision": "",
                "note": "",
            },
        }
    )


def check_fields(value: Any, scopes: list) -> None:
    """Validate shape and exact producer scopes; semantic decisions belong to people."""
    if not isinstance(value, dict) or set(value) != {
        "operation",
        "reviewer",
        "decisions",
        "decision",
        "note",
    }:
        raise ValueError("Invalid literal communication review fields")
    if value["operation"] not in ACTIONS | {""} or value["decision"] not in {
        "",
        "accepted",
        "returned",
        "rejected",
    }:
        raise ValueError("Invalid selected communication operation or decision")
    if any(
        not isinstance(value[k], str) or len(value[k]) > maximum
        for k, maximum in (("reviewer", 200), ("note", 2000))
    ):
        raise ValueError("Invalid communication reviewer or note")
    decisions = value["decisions"]
    if not isinstance(decisions, dict) or set(decisions) - set(scopes):
        raise ValueError(
            "Decision is outside the actual current semantic review matrix"
        )
    for row in decisions.values():
        if (
            not isinstance(row, dict)
            or set(row) != {"decision", "note"}
            or row["decision"] not in {"", "accepted", "returned", "rejected"}
            or not isinstance(row["note"], str)
            or len(row["note"]) > 2000
        ):
            raise ValueError("Invalid scope decision")
    bounded(value)


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    """Serve app-only studio-wide native review, with no Archive relocation."""
    owner, rows = bindings()
    action = tool.removeprefix(PREFIX)
    if action == "catalogue":
        works = []
        for row in rows:
            _, _, page = snapshot(owner, row, module)
            data = page["data"]
            works.append(
                {
                    "work_ref": row["work_ref"],
                    "studio": data["studio"],
                    "run_id": data["run_id"],
                    "objective": data["intake"]["objective"],
                    "recommendation": data["workbench"]["contribution"][
                        "recommendation"
                    ],
                }
            )
        return {
            "works": works,
            "configured": bool(rows),
            "workspace_scope": "studio_wide",
            "initial_authoring_available": False,
            "model_context_transferred": False,
        }
    row = next((row for row in rows if row["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned communication run")
    workspace, run = connection(row, module)
    # Native bookkeeping uses its own writer guard; public commands still take
    # the maintained OS workflow lock. No model or semantic judgment is replaced.
    with api.write_lock(workspace / "native-communication-marker"):
        _, _, page = snapshot(owner, row, module)
        directory = (
            workspace
            / ".native-workspace"
            / ("communication-" + stamp({"owner": owner, "work_ref": row["work_ref"]}))
        )
        regular(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        current = draft(directory)
        operations_path = directory / "operations.json"
        operations = read(operations_path) if operations_path.is_file() else {}
        for key, item in operations.items():
            if (
                item["fingerprint"] != stamp(item["request"])
                or item["request"]["idempotency_key"] != key
            ):
                raise ValueError("Communication intent integrity mismatch")
            if item["status"] == "completed" and item["receipt_sha256"] != stamp(
                item["result"]
            ):
                raise ValueError("Communication receipt integrity mismatch")
        can_write = "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        scopes = page["data"]["workbench"]["required_review_scopes"]
        if action == "setup":
            page.update(
                fields=current["fields"],
                draft_revision=stamp(current),
                draft_stale=bool(
                    current["revision"] and current["revision"] != page["revision"]
                ),
                confirmation_restored=False,
                can_write=can_write,
                pending_operations=[
                    key
                    for key, item in operations.items()
                    if item["status"] == "pending"
                ],
                initial_authoring_available=False,
                sent_or_published=False,
            )
            return json.loads(bounded(page))
        if action == "artifact":
            if any(args[k] != page[k] for k in ("revision", "source_ref")):
                raise ValueError("Communication artifact scope is stale")
            artifact = next(
                (
                    item
                    for item in page["data"]["artifacts"]
                    if item["name"] == args["artifact_ref"]
                ),
                None,
            )
            if artifact is None:
                raise PermissionError(
                    "Select one exact producer-declared artifact; raw history is not available"
                )
            path = run / artifact["name"]
            regular(path)
            if path.stat().st_size > 1_000_000:
                raise ValueError(
                    "Native artifact exceeds complete download limit; use the exact maintained file"
                )
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
                raise ValueError("Communication artifact changed")
            return {
                "name": path.name,
                "sha256": artifact["sha256"],
                "mime_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
                "base64": base64.b64encode(content).decode(),
            }
        if not can_write:
            raise PermissionError(
                "Communication writes require this host's reviewer authority"
            )
        fingerprint = stamp(args)
        if action == "execute" and args["idempotency_key"] in operations:
            previous = operations[args["idempotency_key"]]
            if previous["fingerprint"] != fingerprint:
                raise ValueError("Changed communication retry")
            if previous["status"] != "completed":
                raise ValueError(
                    "Uncertain communication write requires specialist recovery"
                )
            if previous["after_revision"] != page["revision"]:
                raise ValueError("Communication changed after the retained operation")
            return previous["result"]
        if any(args[k] != page[k] for k in ("revision", "source_ref")):
            raise ValueError("Communication scope changed; reopen the exact run")
        if args["expected_draft_revision"] != stamp(current):
            raise ValueError("Communication fields changed in another window")
        if action == "draft_clear":
            if args.get("confirmed") is not True:
                raise ValueError(
                    "Confirm discarding only this owner's unfinished fields"
                )
            next_draft = {
                "generation": current["generation"] + 1,
                "revision": "",
                "fields": {
                    "operation": "",
                    "reviewer": "",
                    "decisions": {},
                    "decision": "",
                    "note": "",
                },
            }
            api.atomic_json(directory / "draft.json", next_draft)
            return {
                "saved": True,
                "draft_revision": stamp(next_draft),
                "confirmation_restored": False,
            }
        if action == "draft_save":
            check_fields(args["fields"], scopes)
            next_draft = {
                "generation": current["generation"] + 1,
                "revision": page["revision"],
                "fields": args["fields"],
            }
            api.atomic_json(directory / "draft.json", next_draft)
            return {
                "saved": True,
                "draft_revision": stamp(next_draft),
                "confirmation_restored": False,
            }
        if action != "execute":
            raise ValueError("Unsupported communication native action")
        if any(item["status"] == "pending" for item in operations.values()):
            raise ValueError(
                "Uncertain communication write requires specialist recovery"
            )
        fields = args["fields"]
        check_fields(fields, scopes)
        if (
            fields != current["fields"]
            or current["revision"] != page["revision"]
            or args.get("confirmed") is not True
            or type(args.get("quality_checklist_confirmed")) is not bool
        ):
            raise ValueError("Confirm the exact current saved communication fields")
        operation = fields["operation"]
        if operation not in ACTIONS:
            raise ValueError("Choose the communication operation")
        if operation.endswith("review") and not fields["reviewer"].strip():
            raise ValueError("Supply the actual professional reviewer")
        if operation == "semantic_review" and (
            set(fields["decisions"]) != set(scopes)
            or any(not item["decision"] for item in fields["decisions"].values())
        ):
            raise ValueError("Review every actual semantic scope exactly once")
        if operation in {"render_review", "package_review"} and (
            not fields["decision"]
            or (
                operation == "render_review"
                and fields["decision"] == "accepted"
                and args["quality_checklist_confirmed"] is not True
            )
        ):
            raise ValueError(
                "Supply the separate artifact decision and required visual checklist"
            )
        key = args["idempotency_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", key):
            raise ValueError("Invalid communication operation key")
        intent = {
            "status": "pending",
            "fingerprint": fingerprint,
            "request": args,
            "before_revision": page["revision"],
        }
        bounded({**operations, key: intent})
        operations[key] = intent
        api.atomic_json(operations_path, operations)
        arguments = {
            "reviewer": fields["reviewer"],
            "decision": fields["decision"],
            "note": fields["note"],
            "quality_checklist_confirmed": args["quality_checklist_confirmed"],
        }
        if operation == "semantic_review":
            bundle = {
                "schema_version": 1,
                "run_id": row["run_id"],
                "decisions": [
                    {"scope": scope, **fields["decisions"][scope]} for scope in scopes
                ],
            }
            bundle_path = directory / ("bundle-" + stamp(bundle) + ".json")
            api.atomic_json(bundle_path, bundle)
            arguments["bundle_path"] = str(bundle_path)
        produced = producer(module, workspace, row, operation, **arguments)
        _, _, after = snapshot(owner, row, module)
        result = {
            "saved": True,
            "operation": operation,
            "work_ref": row["work_ref"],
            "revision": after["revision"],
            "result": produced,
            "sent_or_published": False,
            "model_context_transferred": False,
        }
        intent.update(
            status="completed", after_revision=after["revision"], result=result
        )
        intent["receipt_sha256"] = stamp(result)
        bounded(operations)
        api.atomic_json(operations_path, operations)
        return result
