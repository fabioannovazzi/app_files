"""Native Patent Box operations with exact drafts, prior bytes and recovery intents."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_patent_box_bridge import LIMIT, OPERATIONS

__all__ = ["dispatch", "audit_run"]


def engine(root: Path, request: dict) -> dict:
    """Use the fixed isolated producer adapter, never a caller's module or command."""
    raw = json.dumps(request, ensure_ascii=False, allow_nan=False)
    if len(raw.encode("utf-8")) > LIMIT:
        raise ValueError("Patent Box complete request exceeds native boundary")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_patent_box_bridge.py")),
            str(root),
        ],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Patent Box service refused"
        )
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Check retained originals and all historical receipts before writes or closure."""
    directory = api.ui_state_directory(output, create=False)
    state_path = directory / "patent-box-operations.json"
    state = api.read_json(state_path) if state_path.exists() else {"operations": []}
    home = directory / "patent-box-receipts"
    if home.is_symlink():
        raise ValueError("Linked Patent Box receipt directory")
    references, keys = set(), set()
    current = tree_hash(output)
    recovery = False
    for row in state["operations"]:
        request = row["request"]
        identity = api.digest([request["owner"], row["key"]])
        reference = "operation-" + api.digest([row["key"], request])
        if (
            identity in keys
            or reference in references
            or row["fingerprint"] != api.digest(request)
            or row["snapshot_ref"] != reference
        ):
            raise ValueError("Patent Box operation identity changed")
        keys.add(identity)
        references.add(reference)
        retained = home / reference
        if not retained.is_dir() or tree_hash(retained) != request["before"]:
            raise ValueError("Patent Box retained prior bytes changed")
        if row["status"] not in {"pending", "complete", "refused"}:
            raise ValueError("Invalid Patent Box operation state")
        recovery |= row["status"] == "pending"
        if row["status"] != "pending":
            receipt = row["receipt"]
            if (
                row["receipt_sha256"] != api.digest(receipt)
                or receipt["work_ref"] != request["binding"]["work_ref"]
                or receipt["operation"] != request["action"]
                or receipt["status"] != row["status"]
                or any(
                    current.get(name) != sha for name, sha in receipt["files"].items()
                )
                or any(
                    receipt["files"].get(name) != sha
                    for name, sha in request["before"].items()
                )
                or row["status"] == "refused"
                and receipt["files"] != request["before"]
            ):
                raise ValueError("Patent Box completed receipt or public bytes changed")
    if home.exists():
        recovery |= any(path.name not in references for path in home.iterdir())
    return {"state": state, "recovery_required": recovery}


def literal_fields(value: Any, action: str) -> dict:
    """Save incomplete literal proposals without defaulting meanings or confirmations."""
    if not isinstance(value, dict) or not set(value) <= OPERATIONS[action]:
        raise ValueError("Unexpected Patent Box draft fields")
    if (
        len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        > LIMIT - 10_000
    ):
        raise ValueError("Patent Box draft exceeds complete-record boundary")
    return value


def snapshot(binding: dict, root: Path, action: str, api: Any) -> dict:
    """Reload authoritative ledger and complete public scope on every read and write."""
    if (
        binding["component"] != "patent-box-review"
        or binding["workflow_id"] != "patent-box-review"
        or root.name != "patent-box-review"
    ):
        raise PermissionError("Patent Box belongs to another workflow")
    if action not in OPERATIONS:
        raise ValueError("Unsupported Patent Box operation")
    loaded = api.load_binding(binding)
    output = Path(loaded["output_dir"])
    public = engine(root, {"operation": "read", "context": str(loaded["context_path"])})
    audit = audit_run(output, api)
    owner = [
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
    ]
    identity = json.loads(
        json.dumps(
            {
                "owner": owner,
                "binding": binding,
                "run": loaded["run"],
                "inputs": loaded["input_manifest"],
                "files": public["files"],
                "operation": action,
                "implementation": {
                    "public": engine(root, {"operation": "implementation"}),
                    "native": {
                        path.name: file_hash(path)
                        for path in (
                            Path(__file__),
                            Path(__file__).with_name("native_patent_box_bridge.py"),
                            Path(__file__).parents[1] / "ui/patent-box.js",
                            Path(__file__).parents[1] / "mcp/workspace.cjs",
                        )
                    },
                },
            }
        )
    )
    draft_path = api.ui_state_directory(output, create=False) / (
        "patent-box-draft-" + api.digest([owner, action]) + ".json"
    )
    draft = (
        api.read_json(draft_path)
        if draft_path.exists()
        else {"scope": identity, "generation": 0, "fields": {}}
    )
    if type(draft["generation"]) is not int or draft["generation"] < 0:
        raise ValueError("Invalid Patent Box draft generation")
    literal_fields(draft["fields"], action)
    return {
        "loaded": loaded,
        "output": output,
        "public": public,
        "identity": identity,
        "revision": api.digest(identity),
        "source_ref": api.digest([binding, action, public["files"]]),
        "draft": draft,
        "draft_path": draft_path,
        "draft_revision": api.digest(draft),
        "draft_stale": draft["scope"] != identity,
        "can_write": loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not audit["recovery_required"],
        **audit,
    }


def authority(current: dict, args: dict, *, draft=False) -> None:
    """Exact version and generation CAS are mechanical authorization constraints."""
    if (
        args["revision"] != current["revision"]
        or args["source_ref"] != current["source_ref"]
    ):
        raise ValueError("Patent Box scope changed; reopen exact version")
    if not current["can_write"]:
        raise PermissionError("Patent Box run is read-only or requires recovery")
    if draft and args["expected_draft_revision"] != current["draft_revision"]:
        raise ValueError("Patent Box unfinished fields changed; reopen draft")


def view(current: dict, binding: dict, action: str) -> dict:
    """App-only complete records; no model projection or fabricated authentication."""
    return {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "source_ref": current["source_ref"],
        "operation": action,
        "label": current["loaded"]["run"]["label"],
        "run_status": current["loaded"]["run"]["status"],
        "selected_sources": [
            {
                "binding_id": row["binding_id"],
                "name": Path(row["execution_relative_path"]).name,
                "role": row["role"],
                "sha256": row["sha256"],
                "byte_count": row["byte_count"],
            }
            for row in current["loaded"]["input_manifest"]["inputs"]
        ],
        "data": {"selection": {"source_ref": current["source_ref"]}},
        "session": current["public"]["session"],
        "proposals": current["public"]["proposals"],
        "files": current["public"]["files"],
        "fields": current["draft"]["fields"],
        "draft_revision": current["draft_revision"],
        "draft_stale": current["draft_stale"],
        "can_write": current["can_write"],
        "recovery_required": current["recovery_required"],
        "confirmation_restored": False,
        "model_reads_performed": False,
        "professional_acceptance": False,
        "boundary": "Development preview. Local reviewer assertion cannot authorize real calculation. Current sources, reviewed rules and externally signed firm authorization remain producer requirements. Unsigned Word/PDF drafts, final signed review, formalities and Archive completion are distinct.",
    }


def dispatch(tool: str, args: dict, binding: dict, root: Path, api: Any) -> dict:
    """Keep drafts private and invoke unchanged producers only on renewed app action."""
    operation = args.get("operation", "initialize")
    current = snapshot(binding, root, operation, api)
    action = tool.removeprefix("vera_workspace_patent_box_")
    if action == "setup":
        return view(current, binding, operation)
    if action in {"read", "artifact"}:
        if (
            args["revision"] != current["revision"]
            or args["source_ref"] != current["source_ref"]
        ):
            raise ValueError("Patent Box artifact scope changed")
        name = args["file_ref"]
        extensions = (
            {".pdf", ".docx"}
            if action == "artifact"
            else {".json", ".md", ".csv", ".txt"}
        )
        if (
            name not in current["public"]["files"]
            or Path(name).suffix not in extensions
        ):
            raise ValueError("Choose an existing readable Patent Box artifact")
        path = current["output"] / name
        if path.stat().st_size > (LIMIT * 3 // 4 if action == "artifact" else LIMIT):
            raise ValueError("Patent Box complete artifact exceeds native boundary")
        raw = path.read_bytes()
        content = (
            base64.b64encode(raw).decode("ascii")
            if action == "artifact"
            else raw.decode("utf-8")
        )
        if file_hash(path) != current["public"]["files"][name]:
            raise ValueError("Patent Box artifact changed while reading")
        return {
            "work_ref": binding["work_ref"],
            "file_ref": name,
            "content": content,
            "encoding": "base64" if action == "artifact" else "utf-8",
            "mime_type": (
                "application/pdf"
                if Path(name).suffix == ".pdf"
                else (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    if action == "artifact"
                    else "text/plain;charset=utf-8"
                )
            ),
            "byte_count": len(raw),
            "sha256": current["public"]["files"][name],
            "model_reads_performed": False,
        }
    if action not in {"draft_save", "draft_clear", "execute"}:
        raise ValueError("Unsupported native Patent Box tool")
    with api.write_lock(current["output"]):
        current = snapshot(binding, root, operation, api)
        if action in {"draft_save", "draft_clear"}:
            authority(current, args, draft=True)
            if action == "draft_clear":
                if args.get("confirmed") is not True:
                    raise ValueError(
                        "Confirm discarding only this unfinished Patent Box draft"
                    )
                fields = {}
            else:
                if current["draft_stale"]:
                    raise ValueError("Compare and discard stale Patent Box draft first")
                fields = literal_fields(args["fields"], operation)
            saved = {
                "scope": current["identity"],
                "generation": current["draft"]["generation"] + 1,
                "fields": fields,
            }
            api.atomic_json(
                api.ui_state_directory(current["output"]) / current["draft_path"].name,
                saved,
            )
            return {
                "work_ref": binding["work_ref"],
                "saved": True,
                "draft_revision": api.digest(saved),
                "confirmation_restored": False,
            }
        key = args["idempotency_key"]
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValueError("Patent Box operation needs a bounded idempotency key")
        if args.get("confirmed") is not True:
            raise ValueError(
                "Confirm the exact Patent Box operation and saved fields again"
            )
        request = {
            "binding": binding,
            "owner": current["identity"]["owner"],
            "action": operation,
            "revision": args["revision"],
            "source_ref": args["source_ref"],
            "fields": args["fields"],
            "expected_draft_revision": args["expected_draft_revision"],
        }
        for row in current["state"]["operations"]:
            if row["key"] == key and row["request"]["owner"] == request["owner"]:
                original = {
                    name: value
                    for name, value in row["request"].items()
                    if name != "before"
                }
                if original != request or row["status"] == "pending":
                    raise ValueError(
                        "Patent Box retry conflicts or requires ordinary recovery"
                    )
                return row["receipt"]
        authority(current, args, draft=True)
        fields = literal_fields(args["fields"], operation)
        if (
            set(fields) != OPERATIONS[operation]
            or current["draft_stale"]
            or fields != current["draft"]["fields"]
        ):
            raise ValueError(
                "Save the complete current Patent Box operation before executing"
            )
        if operation != "initialize" and not current["public"]["session"]:
            raise ValueError("Initialize Patent Box in the actual Archive run first")
        # A complete native request must fit before a durable intent can become uncertain.
        engine_request = {
            "operation": operation,
            "context": str(current["loaded"]["context_path"]),
            "fields": fields,
            "expected_files": current["public"]["files"],
        }
        if (
            len(
                json.dumps(engine_request, ensure_ascii=False, allow_nan=False).encode()
            )
            > LIMIT
        ):
            raise ValueError(
                "Patent Box complete operation exceeds native request boundary"
            )
        request["before"] = current["public"]["files"]
        reference = "operation-" + api.digest([key, request])
        directory = api.ui_state_directory(current["output"])
        home = directory / "patent-box-receipts"
        home.mkdir(mode=0o700, exist_ok=True)
        retained = home / reference
        retained.mkdir(mode=0o700)
        for name in request["before"]:
            destination = retained / name
            destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            shutil.copyfile(current["output"] / name, destination)
            destination.chmod(0o600)
        if tree_hash(retained) != request["before"]:
            raise ValueError(
                "Patent Box prior bytes changed during preservation; recovery required"
            )
        row = {
            "key": key,
            "request": request,
            "fingerprint": api.digest(request),
            "snapshot_ref": reference,
            "status": "pending",
        }
        current["state"]["operations"].append(row)
        state_path = directory / "patent-box-operations.json"
        api.atomic_json(state_path, current["state"])
        result = engine(root, engine_request)
        if result["status"] == "uncertain":
            raise ValueError(
                "Patent Box producer partially wrote outputs; ordinary recovery required"
            )
        if tree_hash(current["output"]) != result["files"]:
            raise ValueError(
                "Patent Box public bytes changed before receipt; ordinary recovery required"
            )
        receipt = {
            "work_ref": binding["work_ref"],
            "operation": operation,
            **result,
            "prior_bytes_ref": reference,
            "model_reads_performed": False,
            "professional_acceptance": False,
        }
        row.update(
            status=result["status"], receipt=receipt, receipt_sha256=api.digest(receipt)
        )
        api.atomic_json(state_path, current["state"])
        return receipt
