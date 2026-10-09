"""Explicit registered-table authoring before the public Treasury review service."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["audit_preparation", "dispatch"]

FIELDS = {
    "company_id",
    "company_name",
    "currency",
    "as_of",
    "horizon_end",
    "coverage",
    "tables",
    "invoice_input_ids",
    "previous_input_id",
}


def engine_call(root: Path, request: dict) -> dict:
    """Keep public producer imports and source reads outside shared adapter imports."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_treasury_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Treasury intake refused"
        )
    return json.loads(result.stdout)


def audit_preparation(output: Path, root: Path, api: Any) -> None:
    """Uncertain writes never become reviewable by merely discovering a session."""
    private = api.ui_state_directory(output, create=False)
    requests = list(private.glob("treasury-prepare-request-*.json"))
    if any("result" not in api.read_json(p) for p in requests):
        raise ValueError(
            "Interrupted Treasury preparation requires specialist recovery"
        )
    path = private / "treasury-prepare-state.json"
    if not path.exists():
        if requests:
            raise ValueError("Treasury preparation receipt is missing")
        return
    retained = api.read_json(path)
    if (
        retained["implementation"]
        != engine_call(root, {"operation": "contract"})["implementation"]
    ):
        raise ValueError("Treasury preparation implementation changed")
    version = retained["initial_record_sha256"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
        raise ValueError("Invalid native Treasury initial version")
    if tree_hash(output / "versions" / version) != retained["initial_artifacts"]:
        raise ValueError("Native Treasury initial immutable artifacts changed")
    for name, expected in retained["native_artifacts"].items():
        if (
            name not in {"native_treasury_manifest.json", "native_treasury_intake.json"}
            or file_hash(output / name) != expected
        ):
            raise ValueError("Native Treasury intake evidence changed")
    state = api.read_json(output / "treasury_session.json")
    if version not in state["history"]:
        raise ValueError("Native Treasury initial version is missing from history")


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Hash stable registered choices; public session review remains authoritative."""
    if binding["workflow_id"] != "treasury-forecast":
        raise PermissionError("Treasury intake belongs to another workflow")
    output = Path(loaded["output_dir"])
    contract = engine_call(root, {"operation": "contract"})
    try:
        audit_preparation(output, root, api)
    except ValueError as exc:
        status, issue = "recovery_required", str(exc)
    else:
        status = (
            "prepared"
            if (output / "treasury_session.json").exists()
            else "ready" if not any(output.iterdir()) else "recovery_required"
        )
        issue = (
            "Existing Treasury outputs require specialist recovery"
            if status == "recovery_required"
            else None
        )
        if status == "prepared":
            reviewed = engine_call(root, {"operation": "read", "output": str(output)})
            if not reviewed["ok"]:
                status, issue = "recovery_required", reviewed["error"]
    revision = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            contract["implementation"],
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_treasury_bridge.py")),
        ]
    )
    return {
        "output": output,
        "private": api.ui_state_directory(output, create=False),
        "contract": contract,
        "revision": revision,
        "status": status,
        "issue": issue,
    }


def validate_fields(fields: object, headers: dict) -> dict:
    """Structural bounds only; accounting meaning is supplied and producer-validated."""
    if not isinstance(fields, dict) or set(fields) - FIELDS:
        raise ValueError("Invalid Treasury draft fields")
    if len(json.dumps(fields, ensure_ascii=False).encode("utf-8")) > 96000:
        raise ValueError("Treasury draft is too large")
    for key, value in fields.items():
        if key == "tables":
            if not isinstance(value, dict) or set(value) - set(headers):
                raise ValueError("Choose only the six maintained Treasury table roles")
            for row in value.values():
                if (
                    not isinstance(row, dict)
                    or set(row) - {"input_id", "sheet"}
                    or any(
                        not isinstance(v, str) or len(v) > 4000 for v in row.values()
                    )
                ):
                    raise ValueError("Invalid Treasury table choice")
        elif key == "invoice_input_ids":
            if (
                not isinstance(value, list)
                or len(value) > 500
                or any(not isinstance(v, str) or not v or len(v) > 200 for v in value)
                or len(set(value)) != len(value)
            ):
                raise ValueError("Invalid registered invoice choices")
        elif not isinstance(value, str) or len(value) > 4000:
            raise ValueError("Treasury text fields must be bounded literal strings")
    return fields


def draft_path(current: dict, binding: dict, api: Any) -> Path:
    return current["private"] / (
        "treasury-intake-draft-" + api.digest(owner_scope(binding)) + ".json"
    )


def read_draft(current: dict, binding: dict, api: Any) -> dict:
    path = draft_path(current, binding, api)
    if not path.exists():
        return {"fields": {}, "draft_revision": "", "stale": False}
    value = api.read_json(path)
    if value["owner"] != owner_scope(binding) or value["draft_revision"] != api.digest(
        {k: v for k, v in value.items() if k != "draft_revision"}
    ):
        raise ValueError("Treasury intake draft changed or belongs to another owner")
    return {
        "fields": validate_fields(value["fields"], current["contract"]["headers"]),
        "draft_revision": value["draft_revision"],
        "stale": value["revision"] != current["revision"],
    }


def registered(identity: str, loaded: dict, suffixes: set) -> Path:
    """Exact receipts, never a browser filesystem path or guessed source role."""
    receipt = next(
        (
            row
            for row in loaded["input_manifest"]["inputs"]
            if row["binding_id"] == identity
        ),
        None,
    )
    if receipt is None:
        raise PermissionError("Treasury input is outside this run")
    path = Path(loaded["run_root"]) / receipt["execution_relative_path"]
    if path.suffix.lower() not in suffixes or file_hash(path) != receipt["sha256"]:
        raise ValueError(
            "Treasury selected source differs from its registered receipt or format"
        )
    return path


def compile_manifest(fields: dict, current: dict, loaded: dict, root: Path) -> dict:
    """Encode the maintained manifest from explicit portable receipt identities."""
    required = FIELDS - {"previous_input_id", "invoice_input_ids"}
    if (
        required - set(fields)
        or any(not fields[key].strip() for key in required - {"tables"})
        or set(fields["tables"]) != set(current["contract"]["headers"])
    ):
        raise ValueError(
            "Declare company, currency, cutoff, horizon, coverage and all six table roles"
        )
    inputs = Path(loaded["run_root"]) / "inputs"
    manifest = {
        "schema_version": "vera.treasury_manifest.v1",
        **{key: fields[key] for key in required - {"tables"}},
        "tables": {},
        "invoice_files": [],
        "previous": None,
    }
    for name, choice in fields["tables"].items():
        path = registered(choice.get("input_id", ""), loaded, {".csv", ".xlsx"})
        item = {"path": path.relative_to(inputs).as_posix()}
        if choice.get("sheet"):
            item["sheet"] = choice["sheet"]
        manifest["tables"][name] = item
    for identity in fields.get("invoice_input_ids", []):
        path = registered(identity, loaded, {".xml"})
        manifest["invoice_files"].append(path.relative_to(inputs).as_posix())
    if fields.get("previous_input_id"):
        path = registered(fields["previous_input_id"], loaded, {".json"})
        predecessor = engine_call(root, {"operation": "predecessor", "path": str(path)})
        manifest["previous"] = {
            "path": path.relative_to(inputs).as_posix(),
            "record_sha256": predecessor["record_sha256"],
        }
    return manifest


def inspected(
    fields: dict, args: dict, current: dict, loaded: dict, root: Path
) -> tuple[dict, dict]:
    manifest = compile_manifest(fields, current, loaded, root)
    table = args.get("table")
    offset = args.get("offset", 0)
    if (
        table is not None
        and table not in current["contract"]["headers"]
        or isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
    ):
        raise ValueError("Invalid Treasury source page")
    result = engine_call(
        root,
        {
            "operation": "inspect",
            "manifest": manifest,
            "context": str(loaded["context_path"]),
            "table": table,
            "offset": offset,
        },
    )
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 100000:
        raise ValueError(
            "Treasury source page exceeds the private UI limit; inspect this source in the specialist workflow"
        )
    return manifest, result


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Prepare once from confirmed sources, then hand back to the public review flow."""
    current = context(binding, loaded, root, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_treasury_setup":
        offset = args.get("offset", 0)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("Invalid Treasury source offset")
        items = [
            {
                "id": row["binding_id"],
                "title": Path(row["execution_relative_path"]).name,
                "kind": Path(row["execution_relative_path"]).suffix.lower(),
            }
            for row in loaded["input_manifest"]["inputs"]
        ]
        return {
            "work_ref": args["work_ref"],
            "label": loaded["run"]["label"],
            "revision": current["revision"],
            "status": current["status"],
            "issue": current["issue"],
            "can_prepare": writable and current["status"] == "ready",
            "items": items[offset : offset + 30],
            "has_more": offset + 30 < len(items),
            "total": len(items),
            "headers": current["contract"]["headers"],
            "draft": read_draft(current, binding, api),
        }
    if tool == "vera_workspace_treasury_inspect":
        draft = read_draft(current, binding, api)
        if (
            args["revision"] != current["revision"]
            or args["expected_draft_revision"] != draft["draft_revision"]
            or draft["stale"]
        ):
            raise ValueError("Stale Treasury intake selection")
        _, result = inspected(draft["fields"], args, current, loaded, root)
        api.load_binding(binding)
        return {
            **result,
            "work_ref": args["work_ref"],
            "revision": current["revision"],
            "draft_revision": draft["draft_revision"],
        }
    if not writable:
        raise PermissionError(
            "A running Treasury run and reviewer authority are required"
        )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if loaded["run"]["status"] != "running":
            raise PermissionError("Treasury run is no longer running")
        if tool == "vera_workspace_treasury_prepare":
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid Treasury preparation request key")
            fingerprint = api.digest([tool, owner_scope(binding), args])
            intent = current["private"] / (
                "treasury-prepare-request-"
                + api.digest([owner_scope(binding), key])
                + ".json"
            )
            if intent.exists():
                previous = api.read_json(intent)
                if previous["request_sha256"] != fingerprint:
                    raise ValueError(
                        "Treasury preparation key belongs to a different request"
                    )
                if "result" not in previous:
                    raise ValueError(
                        "Interrupted Treasury preparation requires specialist recovery"
                    )
                audit_preparation(current["output"], root, api)
                return previous["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Stale Treasury preparation")
        draft = read_draft(current, binding, api)
        if args["expected_draft_revision"] != draft["draft_revision"]:
            raise ValueError("Treasury intake draft changed; reopen it")
        path = draft_path(current, binding, api)
        if tool == "vera_workspace_treasury_draft_clear":
            path.unlink(missing_ok=True)
            return {"saved": True, "draft_revision": "", "status": "draft_cleared"}
        if current["status"] != "ready":
            raise ValueError(
                "Existing Treasury session or outputs require review or specialist recovery"
            )
        if tool == "vera_workspace_treasury_draft_save":
            fields = validate_fields(args["fields"], current["contract"]["headers"])
            value = {
                "schema_version": "vera.native_treasury_intake_draft.v1",
                "owner": owner_scope(binding),
                "revision": current["revision"],
                "fields": fields,
            }
            value["draft_revision"] = api.digest(value)
            api.atomic_json(path, value)
            return {
                "saved": True,
                "status": "draft_saved",
                "draft_revision": value["draft_revision"],
            }
        if (
            tool != "vera_workspace_treasury_prepare"
            or args.get("human_reviewed") is not True
            or draft["stale"]
        ):
            raise ValueError(
                "Confirm the exact current saved Treasury choices before preparation"
            )
        manifest, preflight = inspected(draft["fields"], {}, current, loaded, root)
        if not preflight["ok"]:
            raise ValueError(preflight["error"])
        api.load_binding(binding)
        api.atomic_json(intent, {"request_sha256": fingerprint})
        output = current["output"]
        api.atomic_json(output / "native_treasury_manifest.json", manifest)
        api.atomic_json(
            output / "native_treasury_intake.json",
            {
                "schema_version": "vera.native_treasury_intake.v1",
                "owner": owner_scope(binding),
                "draft_revision": draft["draft_revision"],
                "fields": draft["fields"],
                "input_manifest_sha256": api.digest(loaded["input_manifest"]),
                "human_confirmed_preparation": True,
                "professional_approval": False,
                "implementation": current["contract"]["implementation"],
            },
        )
        prepared = engine_call(
            root,
            {
                "operation": "prepare",
                "context": str(loaded["context_path"]),
                "manifest_path": str(output / "native_treasury_manifest.json"),
                "output": str(output),
            },
        )
        api.load_binding(binding)
        if engine_call(root, {"operation": "contract"}) != current["contract"]:
            raise ValueError("Treasury implementation changed during preparation")
        if prepared["status"] == "accepted":
            raise ValueError("Treasury preparation unexpectedly approved a forecast")
        retained = {
            "initial_record_sha256": prepared["record_sha256"],
            "implementation": current["contract"]["implementation"],
            "initial_artifacts": tree_hash(
                output / "versions" / prepared["record_sha256"]
            ),
            "native_artifacts": {
                name: file_hash(output / name)
                for name in (
                    "native_treasury_manifest.json",
                    "native_treasury_intake.json",
                )
            },
        }
        api.atomic_json(current["private"] / "treasury-prepare-state.json", retained)
        result = {
            "saved": True,
            **prepared,
            "professional_approval": False,
            "run_completed": False,
        }
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        audit_preparation(output, root, api)
        return result
