"""Private grant-dossier views and explicit literal review over public contracts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "audit_run"]

SCOPES = {"initialization", "source_baseline", "requirements", "assessments", "dossier"}
RECORDS = (
    "case_intake",
    "source_register",
    "application_workbench",
    "intelligence_register",
    "review_log",
    "run_state",
)


def stamp(value: Any) -> str:
    """Stable JSON identity required by exact scope and receipt contracts."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def engine(root: Path, request: dict) -> dict:
    """Use a fixed isolated local script; no provider, browser, or arbitrary command."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_bandi_bridge.py")),
            str(root),
        ],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Grant operation refused"
        )
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Retained prior bytes and pending intents govern ordinary recovery and closure."""
    directory = api.ui_state_directory(output, create=False)
    path = directory / "bandi-operations.json"
    state = api.read_json(path) if path.exists() else {"operations": []}
    home = directory / "bandi-receipts"
    references, keys = set(), set()
    recovery = False
    for row in state["operations"]:
        if row["key"] in keys or row["fingerprint"] != stamp(row["request"]):
            raise ValueError("Grant operation identity changed")
        keys.add(row["key"])
        reference = "operation-" + stamp([row["key"], row["request"]])
        if reference != row["snapshot_ref"] or reference in references:
            raise ValueError("Grant retained-version identity changed")
        references.add(reference)
        if row["status"] not in {"pending", "complete"}:
            raise ValueError("Invalid grant operation state")
        recovery |= row["status"] == "pending"
        retained = home / reference
        if not retained.is_dir() or tree_hash(retained) != row["request"]["before"]:
            raise ValueError("Grant retained prior bytes changed")
        if row["status"] == "complete":
            receipt = row["receipt"]
            if (
                row["receipt_sha256"] != stamp(receipt)
                or receipt["work_ref"] != row["request"]["binding"]["work_ref"]
                or receipt["public_operation"] != row["request"]["action"]
            ):
                raise ValueError("Grant operation receipt changed")
            if receipt["public_operation"] == "review":
                log = api.read_json(output / "review_log.json")
                if receipt["public_result"] not in log["events"]:
                    raise ValueError("Recorded grant professional event changed")
    if home.exists():
        recovery |= any(path.name not in references for path in home.iterdir())
    return {"state": state, "recovery_required": recovery}


def fields(value: Any, scope: str) -> dict:
    """Preserve incomplete literal fields; never fill a decision or infer identity."""
    names = (
        {"reference_date", "client_reference", "language"}
        if scope == "initialization"
        else {"decision", "reviewer_id", "reviewer_role", "notes"}
    )
    if (
        not isinstance(value, dict)
        or set(value) != names
        or any(not isinstance(v, str) or len(v) > 4000 for v in value.values())
    ):
        raise ValueError("Invalid literal grant draft")
    if scope != "initialization" and value["decision"] not in {
        "",
        "accepted",
        "returned",
    }:
        raise ValueError("Unsupported professional grant decision")
    return value


def snapshot(binding: dict, loaded: dict, root: Path, scope: str, api: Any) -> dict:
    output = Path(loaded["output_dir"])
    public = engine(root, {"operation": "read", "context": str(loaded["context_path"])})
    audit = audit_run(output, api)
    identity = json.loads(
        json.dumps(
            {
                "owner": [
                    os.environ["VERA_WORKSPACE_TENANT_ID"],
                    os.environ["VERA_WORKSPACE_ACTOR_ID"],
                ],
                "binding": binding,
                "run": loaded["run"],
                "inputs": loaded["input_manifest"],
                "outputs": public["files"],
                "scope": scope,
                "public_scope_sha256": public["scope_hashes"].get(scope),
                "implementation": {
                    "public": engine(root, {"operation": "implementation"}),
                    "native": {
                        p.name: file_hash(p)
                        for p in (
                            Path(__file__),
                            Path(__file__).with_name("native_bandi_bridge.py"),
                            Path(__file__).parents[1] / "mcp/workspace.cjs",
                            Path(__file__).parents[1] / "ui/workspace.js",
                        )
                    },
                },
            }
        )
    )
    directory = api.ui_state_directory(output, create=False)
    draft_path = directory / (
        "bandi-draft-" + stamp([identity["owner"], scope]) + ".json"
    )
    empty = (
        {"reference_date": "", "client_reference": "", "language": "it"}
        if scope == "initialization"
        else {"decision": "", "reviewer_id": "", "reviewer_role": "", "notes": ""}
    )
    draft = (
        api.read_json(draft_path)
        if draft_path.exists()
        else {"scope": identity, "generation": 0, "fields": empty}
    )
    fields(draft["fields"], scope)
    can_write = (
        loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not audit["recovery_required"]
        and not public["schema_issues"]
    )
    return {
        "output": output,
        "public": public,
        "identity": identity,
        "revision": stamp(identity),
        "source_ref": stamp([binding, scope, public["files"]]),
        "draft": draft,
        "draft_path": draft_path,
        "draft_revision": stamp(draft),
        "draft_stale": draft["scope"] != identity,
        "can_write": can_write,
        **audit,
    }


def authority(current: dict, args: dict, *, draft: bool = False) -> None:
    if (
        args["revision"] != current["revision"]
        or args["source_ref"] != current["source_ref"]
    ):
        raise ValueError("Grant dossier changed; reopen the exact scope")
    if not current["can_write"]:
        raise PermissionError("This grant run is read-only or needs ordinary recovery")
    if draft and args["expected_draft_revision"] != current["draft_revision"]:
        raise ValueError("Grant unfinished fields changed; reopen the saved draft")


def view(current: dict, binding: dict, scope: str) -> dict:
    public = current["public"]
    if scope == "source_baseline":
        names = ["source_register"]
    elif scope == "requirements":
        names = ["case_intake", "source_register", "application_workbench"]
    else:
        names = list(RECORDS)
    files = [
        {
            "name": name + ".json",
            "bytes": (current["output"] / (name + ".json")).stat().st_size,
            "sha256": public["files"][name + ".json"],
        }
        for name in names
        if name in public["records"]
    ]
    return {
        "work_ref": binding["work_ref"],
        "scope": scope,
        "revision": current["revision"],
        "source_ref": current["source_ref"],
        "data": {"selection": {"source_ref": current["source_ref"]}},
        "setup_status": "dossier_available" if public["initialized"] else "empty_run",
        "can_write": current["can_write"],
        "recovery_required": current["recovery_required"],
        "fields": current["draft"]["fields"],
        "draft_revision": current["draft_revision"],
        "draft_stale": current["draft_stale"],
        "confirmation_restored": False,
        "scope_sha256": public["scope_hashes"].get(scope),
        "files": files,
        "schema_issues": public["schema_issues"],
        "audit": public["audit"],
        "audit_current": public["audit_current"],
        "package_current": public["package_current"],
        "manifest": public["manifest"],
        "operations": [
            row["receipt"]
            for row in current["state"]["operations"]
            if row["status"] == "complete"
        ],
        "ready_to_file": False,
        "model_reads_performed": False,
        "professional_identity_assurance": "asserted_not_authenticated",
        "individual_record_confirmation_performed": False,
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Bind private interaction to one actual run; all semantic work stays in public Bandi."""
    if (
        binding["workflow_id"] != "bandi-agevolazioni"
        or binding["component"] != "bandi-agevolazioni"
    ):
        raise PermissionError("Selected work is not a grant dossier")
    scope = args.get("scope", "dossier")
    if scope not in SCOPES:
        raise ValueError("Unsupported grant review scope")
    current = snapshot(binding, loaded, root, scope, api)
    action = tool.removeprefix("vera_workspace_bandi_")
    if action == "setup":
        return view(current, binding, scope)
    if action == "read":
        if (
            args["revision"] != current["revision"]
            or args["source_ref"] != current["source_ref"]
        ):
            raise ValueError("Grant selected file changed")
        name = args["file_name"]
        if (
            name
            not in {name + ".json" for name in RECORDS}
            | {
                "validation_audit.json",
                "dossier_manifest.json",
                "review_dossier.html",
                "review_dossier.md",
            }
            or name not in current["public"]["files"]
        ):
            raise ValueError("Choose an existing public grant artifact")
        path = current["output"] / name
        if path.stat().st_size > 2_000_000:
            raise ValueError("Grant artifact exceeds the complete-file boundary")
        content = path.read_text(encoding="utf-8")
        if file_hash(path) != current["public"]["files"][name]:
            raise ValueError("Grant artifact changed while reading")
        return {
            "work_ref": binding["work_ref"],
            "file_name": name,
            "path": str(path),
            "content": content,
            "sha256": current["public"]["files"][name],
            "package_current": current["public"]["package_current"],
            "model_reads_performed": False,
        }
    with api.write_lock(current["output"]):
        current = snapshot(binding, loaded, root, scope, api)
        if action in {"draft_save", "draft_clear"}:
            authority(current, args, draft=True)
            if action == "draft_save":
                if current["draft_stale"]:
                    raise ValueError(
                        "Compare and discard stale unfinished grant fields first"
                    )
                value = fields(args["fields"], scope)
            else:
                if args.get("confirmed") is not True:
                    raise ValueError(
                        "Confirm discarding only your unfinished grant fields"
                    )
                value = (
                    {"reference_date": "", "client_reference": "", "language": "it"}
                    if scope == "initialization"
                    else {
                        "decision": "",
                        "reviewer_id": "",
                        "reviewer_role": "",
                        "notes": "",
                    }
                )
            saved = {
                "scope": current["identity"],
                "generation": current["draft"]["generation"] + 1,
                "fields": value,
            }
            path = (
                api.ui_state_directory(current["output"]) / current["draft_path"].name
            )
            api.atomic_json(path, saved)
            return {
                "saved": True,
                "work_ref": binding["work_ref"],
                "revision": current["revision"],
                "draft_revision": stamp(saved),
                "confirmation_restored": False,
            }
        if action not in {"initialize", "review", "validate", "package"}:
            raise ValueError("Unsupported grant native action")
        key = args["idempotency_key"]
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValueError("Grant operation needs a bounded idempotency key")
        request = {
            "binding": binding,
            "owner": current["identity"]["owner"],
            "action": action,
            "revision": args["revision"],
            "source_ref": args["source_ref"],
            "scope": scope,
            "fields": args.get("fields"),
            "expected_draft_revision": args.get("expected_draft_revision"),
        }
        for row in current["state"]["operations"]:
            if row["key"] == key:
                original = {k: v for k, v in row["request"].items() if k != "before"}
                if original != request or row["status"] != "complete":
                    raise ValueError(
                        "Grant operation retry conflicts or needs ordinary recovery"
                    )
                return row["receipt"]
        authority(current, args, draft=action in {"initialize", "review"})
        if action in {"initialize", "review"}:
            if args.get("confirmed") is not True or current["draft_stale"]:
                raise ValueError(
                    "Confirm the current complete grant scope and literal fields again"
                )
            value = fields(args["fields"], scope)
            if value != current["draft"]["fields"]:
                raise ValueError("Save the literal grant fields before recording them")
            if (action == "initialize") != (scope == "initialization"):
                raise ValueError(
                    "Grant action does not match the selected public scope"
                )
            engine(root, {"operation": "preflight", "scope": scope, "fields": value})
        if action == "initialize" and current["public"]["files"]:
            raise ValueError(
                "Existing grant output files require ordinary continuation"
            )
        if action != "initialize" and not current["public"]["initialized"]:
            raise ValueError("Initialize the actual grant run first")
        if action == "package" and not (
            current["public"]["audit_current"]
            and current["public"]["audit"]["status"] == "passed"
        ):
            raise ValueError(
                "Packaging requires a current passing public validation audit"
            )
        request["before"] = current["public"]["files"]
        reference = "operation-" + stamp([key, request])
        directory = api.ui_state_directory(current["output"])
        home = directory / "bandi-receipts"
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
                "Grant prior bytes changed during preservation; ordinary recovery required"
            )
        row = {
            "key": key,
            "request": request,
            "fingerprint": stamp(request),
            "snapshot_ref": reference,
            "status": "pending",
        }
        current["state"]["operations"].append(row)
        state_path = directory / "bandi-operations.json"
        api.atomic_json(state_path, current["state"])
        result = engine(
            root,
            {
                "operation": action,
                "context": str(loaded["context_path"]),
                "expected_files": request["before"],
                "scope": scope,
                "scope_sha256": current["public"]["scope_hashes"].get(scope),
                "fields": request["fields"],
            },
        )
        after = result.pop("files")
        allowed = (
            {name + ".json" for name in RECORDS}
            if action == "initialize"
            else (
                {"review_log.json", "run_state.json"}
                if action == "review"
                else (
                    {"validation_audit.json"}
                    if action == "validate"
                    else {
                        "review_dossier.html",
                        "review_dossier.md",
                        "dossier_manifest.json",
                    }
                )
            )
        )
        if any(
            after.get(name) != request["before"].get(name)
            for name in (set(after) | set(request["before"])) - allowed
        ):
            raise ValueError(
                "Other grant outputs changed during the public operation; ordinary recovery required"
            )
        receipt = {
            "work_ref": binding["work_ref"],
            "public_operation": action,
            "public_result": result,
            "preserved_before": request["before"],
            "after_files": after,
            "snapshot_ref": reference,
            "ready_to_file": False,
            "model_reads_performed": False,
            "individual_record_confirmation_performed": False,
        }
        row.update(status="complete", receipt=receipt, receipt_sha256=stamp(receipt))
        api.atomic_json(state_path, current["state"])
        audit_run(current["output"], api)
        return receipt
