"""Owned registered reporting/costing execution without semantic substitutions.

Receipt identity, tree hashes, fixed public producer status and CAS are
mechanically verifiable audit contracts. The model/professional selects source
roles, classifications, methods, assumptions and interpretation.
"""

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
from native_variance import bounded, offset, read_page, selected

__all__ = ["audit_run", "dispatch"]
FIELDS = {"mode", "input_ids", "recipe_input_id"}
NORMAL_OUTPUTS = {
    "management_control_pack.json",
    "management_control_pack.xlsx",
    "management_control_facts.md",
    "management_control_dashboard.html",
    "execution_receipt.json",
    "model_context.json",
    "model_context_receipt.json",
    "commentary_template.json",
}


def bridge(root: Path, request: dict) -> dict:
    """Use the same declared runtime and isolated unchanged public entry points."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_management_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1] or "Management producer refused"
        )
    return json.loads(completed.stdout)


def fields(value: Any, *, final: bool = False) -> dict:
    """Keep literal mode and exact receipt choices; never assign semantic roles."""
    if (
        not isinstance(value, dict)
        or set(value) != FIELDS
        or value["mode"] not in {"", "reporting", "costing"}
        or not isinstance(value["recipe_input_id"], str)
        or len(value["recipe_input_id"]) > 200
        or not isinstance(value["input_ids"], list)
        or len(value["input_ids"]) > 1000
        or any(
            not isinstance(item, str) or not item or len(item) > 200
            for item in value["input_ids"]
        )
        or len(set(value["input_ids"])) != len(value["input_ids"])
    ):
        raise ValueError(
            "Use literal reporting/costing mode and unique registered input IDs"
        )
    if final and (
        not value["mode"] or not value["input_ids"] or not value["recipe_input_id"]
    ):
        raise ValueError(
            "Choose the professional path, exact sources and reviewed recipe/case"
        )
    return {**value, "input_ids": list(value["input_ids"])}


def selection(value: dict, loaded: dict, api: Any) -> tuple[list[Path], Path, dict]:
    value = fields(value, final=True)
    if value["recipe_input_id"] in value["input_ids"]:
        raise ValueError("Keep source receipts distinct from the reviewed case/recipe")
    sources = [selected(identity, loaded)[0] for identity in value["input_ids"]]
    recipe = selected(value["recipe_input_id"], loaded)[0]
    if recipe.suffix.lower() != ".json":
        raise ValueError("Select the registered complete public JSON recipe/case")
    # Public producers validate the reviewed schema, evidence, roles and scope.
    return sources, recipe, api.read_json(recipe)


def audit_run(output: Path, api: Any) -> dict:
    """Do not adopt partial normal outputs or repeat incomplete executions."""
    private = api.ui_state_directory(output, create=False)
    path = private / "management-state.json"
    saved = api.read_json(path) if path.exists() else None
    requests = [api.read_json(p) for p in private.glob("management-request-*.json")]
    known = saved["generation"] if saved else None
    if saved:
        if (
            not re.fullmatch(r"management-[0-9a-f]{64}", known)
            or tree_hash(output / known) != saved["artifacts"]
            or {p.name for p in (output / known).iterdir()} != NORMAL_OUTPUTS
        ):
            raise ValueError("Management complete artifact bytes or population changed")
    recovery = any("result" not in row for row in requests)
    recovery |= bool(saved) and not any(
        row.get("result", {}).get("source_ref") == known for row in requests
    )
    recovery |= any(p.name != known for p in output.glob("management-*"))
    return {"private": private, "saved": saved, "recovery_required": recovery}


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Separate stable receipt identity from mutable Archive lifecycle metadata."""
    if binding["workflow_id"] != "management-control-pack":
        raise PermissionError("Choose an owned Management Control Pack run")
    output = Path(loaded["output_dir"])
    current = audit_run(output, api)
    implementation = {
        "public": bridge(root, {"operation": "contract"}),
        "native": {
            name: file_hash(Path(__file__).with_name(name))
            for name in (
                "native_management_execution.py",
                "native_management_bridge.py",
                "native_bank_preparation.py",
                "native_sales_plan_authoring.py",
                "native_variance.py",
            )
        },
    }
    stable = {
        "owner": owner_scope(binding),
        "inputs": loaded["input_manifest"],
        "implementation": implementation,
    }
    saved = current["saved"]
    if saved:
        if saved["scope"] != stable:
            raise ValueError(
                "Management conserved calculation belongs to a changed exact scope"
            )
        selection(saved["fields"], loaded, api)
    path = current["private"] / (
        "management-draft-" + api.digest(stable["owner"]) + ".json"
    )
    draft = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": stable,
            "generation": 0,
            "fields": {"mode": "", "input_ids": [], "recipe_input_id": ""},
        }
    )
    if draft["scope"] != stable:
        raise ValueError(
            "Management private draft belongs to changed sources or implementation"
        )
    fields(draft["fields"])
    current.update(
        output=output,
        stable=stable,
        scope={**stable, "run": loaded["run"]},
        implementation=implementation,
        draft_path=path,
        draft=draft,
        draft_revision=api.digest(draft),
    )
    current["revision"] = api.digest([current["scope"], saved])
    return current


def directory(current: dict, args: dict) -> Path:
    if (
        current["recovery_required"]
        or not current["saved"]
        or args.get("source_ref") != current["saved"]["generation"]
    ):
        raise ValueError(
            "Choose the exact complete Management calculation or recover interrupted execution"
        )
    return current["output"] / current["saved"]["generation"]


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Execute both professional paths, retaining all eight unchanged normal outputs."""
    action = tool.removeprefix("vera_workspace_management_")
    current = context(binding, loaded, root, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if action == "setup":
        rows = [
            {
                "id": r["binding_id"],
                "name": Path(r["execution_relative_path"]).name,
                "suffix": Path(r["execution_relative_path"]).suffix.lower(),
            }
            for r in loaded["input_manifest"]["inputs"]
        ]
        start = offset(args)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "status": (
                    "recovery_required"
                    if current["recovery_required"]
                    else "prepared" if current["saved"] else "ready"
                ),
                "can_prepare": writable
                and not current["saved"]
                and not current["recovery_required"],
                "draft": current["draft"]["fields"],
                "draft_revision": current["draft_revision"],
                "source_ref": (
                    current["saved"]["generation"] if current["saved"] else None
                ),
                "mode": (
                    current["saved"]["fields"]["mode"] if current["saved"] else None
                ),
                "calculation": current["saved"]["result"] if current["saved"] else None,
                "items": rows[start : start + 30],
                "total": len(rows),
                "has_more": start + 30 < len(rows),
                "professional_approval": False,
                "run_completed": False,
            }
        )
    if action != "prepare" and args["revision"] != current["revision"]:
        raise ValueError("Reopen the exact current Management selection")
    if action == "case":
        sources, recipe, payload = selection(args["fields"], loaded, api)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "mode": args["fields"]["mode"],
                "case": payload,
                "sources": [{"name": p.name, "sha256": file_hash(p)} for p in sources],
                "recipe_sha256": file_hash(recipe),
                "professional_approval": False,
                "run_completed": False,
            },
            maximum=256000,
        )
    if action in {"draft_save", "prepare"}:
        if not writable or current["recovery_required"]:
            raise PermissionError(
                "Management requires an owned running reviewer and unambiguous execution"
            )
        with api.write_lock(current["output"]):
            latest = context(binding, api.load_binding(binding), root, api)
            if action == "draft_save" and latest["revision"] != args["revision"]:
                raise ValueError("Management scope changed before writing")
            value = fields(args["fields"], final=action == "prepare")
            if action == "draft_save":
                if (
                    latest["saved"]
                    or latest["draft_revision"] != args["expected_draft_revision"]
                ):
                    raise ValueError(
                        "Management draft changed or its calculation is already conserved"
                    )
                draft = {
                    "scope": latest["stable"],
                    "generation": latest["draft"]["generation"] + 1,
                    "fields": value,
                }
                api.atomic_json(latest["draft_path"], draft)
                return {
                    "saved": True,
                    "draft_revision": api.digest(draft),
                    "professional_approval": False,
                }
            if args.get("confirmed") is not True:
                raise PermissionError(
                    "Renew confirmation of exact reviewed Management inputs"
                )
            key = args["idempotency_key"]
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid Management request identity")
            intent = latest["private"] / (
                "management-request-"
                + api.digest([latest["stable"]["owner"], key])
                + ".json"
            )
            fingerprint = api.digest([latest["scope"], value])
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != fingerprint
                    or "result" not in previous
                ):
                    raise ValueError(
                        "Changed or uncertain Management retry requires recovery"
                    )
                return previous["result"]
            if (
                latest["revision"] != args["revision"]
                or latest["saved"]
                or value != latest["draft"]["fields"]
                or latest["draft_revision"] != args["expected_draft_revision"]
            ):
                raise ValueError(
                    "Choose only the exact saved current Management draft before calculation"
                )
            sources, recipe, _ = selection(value, api.load_binding(binding), api)
            generation = "management-" + fingerprint
            output = latest["output"] / generation
            api.atomic_json(intent, {"request_sha256": fingerprint})
            calculated = bridge(
                root,
                {
                    "operation": "prepare",
                    "mode": value["mode"],
                    "inputs": [str(p) for p in sources],
                    "recipe": str(recipe),
                    "context": loaded["context_path"],
                    "output": str(output),
                },
            )
            if {p.name for p in output.iterdir()} != NORMAL_OUTPUTS:
                raise ValueError(
                    "The complete ordinary Management output population is required"
                )
            after = context(binding, api.load_binding(binding), root, api)
            if after["scope"] != latest["scope"]:
                raise ValueError(
                    "Management scope changed during calculation; require recovery"
                )
            result = {
                "work_ref": args["work_ref"],
                "source_ref": generation,
                "saved": True,
                "mode": value["mode"],
                **calculated,
                "professional_approval": False,
                "run_completed": False,
            }
            api.atomic_json(
                latest["private"] / "management-state.json",
                {
                    "generation": generation,
                    "scope": latest["stable"],
                    "fields": value,
                    "artifacts": tree_hash(output),
                    "result": result,
                },
            )
            api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
            return result
    folder = directory(current, args)
    if action == "outputs":
        return bounded(
            {
                "work_ref": args["work_ref"],
                "outputs": [
                    {
                        "name": p.name,
                        "path": str(p),
                        "sha256": file_hash(p),
                        "byte_count": p.stat().st_size,
                    }
                    for p in sorted(folder.iterdir())
                ],
            }
        )
    if action == "read":
        return {
            "work_ref": args["work_ref"],
            "source_ref": args["source_ref"],
            "artifact_name": args["artifact_name"],
            **read_page(folder, args["artifact_name"], offset(args), api),
        }
    if action == "context":
        return bounded(
            {
                "work_ref": args["work_ref"],
                "source_ref": args["source_ref"],
                "revision": current["revision"],
                "evidence_status": "untrusted_exact_generated_management_context",
                **bridge(root, {"operation": "context", "output": str(folder)}),
            },
            maximum=256000,
        )
    raise ValueError("Unknown Management native action")
