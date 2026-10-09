"""Exact registered reviewed-case execution through the eight unchanged public recipes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_financial_analysis import read_prepared

__all__ = ["audit_run", "dispatch", "read_version"]


def bridge(root: Path, request: dict) -> dict:
    """The maintained public CLI owns validation, exact arithmetic and normal outputs."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_financial_execution_bridge.py")),
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
            result.stderr.strip().splitlines()[-1] or "Financial Analysis refused"
        )
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Complete immutable trees and intents prevent partial output adoption and closure."""
    private = api.ui_state_directory(output, create=False)
    state = (
        api.read_json(private / "financial-state.json")
        if (private / "financial-state.json").exists()
        else {"versions": []}
    )
    known = set()
    for row in state["versions"]:
        identity = row["source_ref"]
        if not re.fullmatch(r"financial-[0-9a-f]{64}", identity) or identity in known:
            raise ValueError("Invalid or duplicate Financial Analysis revision")
        known.add(identity)
        if tree_hash(output / identity) != row["artifacts"]:
            raise ValueError("Financial Analysis version artifacts changed")
    uncertain = any(
        "result" not in api.read_json(p)
        for p in private.glob("financial-request-*.json")
    )
    from native_financial_sources import audit_sources

    evidence = audit_sources(output, api)
    known.update(row["grant_ref"] for row in evidence["rows"])
    from native_financial_authoring import audit_authoring

    authoring = audit_authoring(output, api)
    known.update(row["case_ref"] for row in authoring["state"]["cases"])
    return {
        "state": state,
        "evidence": evidence["rows"],
        "authoring": authoring["state"],
        "pending_authoring": authoring["pending"],
        "recovery_required": uncertain
        or evidence["recovery_required"]
        or authoring["recovery_required"]
        or any(p.name not in known for p in output.glob("financial-*")),
    }


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    if binding["workflow_id"] != "financial-analysis":
        raise PermissionError("Choose an owned Financial Analysis run")
    output = Path(loaded["output_dir"])
    audit = audit_run(output, api)
    owner = [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[binding[k] for k in ("client_id", "engagement_id", "run_id", "workflow_id")],
    ]
    info = bridge(root, {"operation": "info"})
    implementation = {
        "public": info,
        **{
            name: file_hash(Path(__file__).with_name(name))
            for name in (
                "native_financial_execution.py",
                "native_financial_execution_bridge.py",
                "native_financial_analysis.py",
                "native_financial_sources.py",
                "native_financial_sources_bridge.py",
                "native_financial_authoring.py",
                "native_financial_author_bridge.py",
            )
        },
    }
    for row in audit["state"]["versions"]:
        if row["owner"] != owner or row["implementation"] != implementation:
            raise PermissionError(
                "Financial Analysis revision belongs to another owner or implementation"
            )
        if row["inputs"] != loaded["input_manifest"]:
            raise ValueError("Financial Analysis input population changed")
    for row in audit["evidence"]:
        if (
            row["owner"] != owner
            or row["implementation"] != implementation
            or row["inputs"] != loaded["input_manifest"]
        ):
            raise PermissionError("Financial source request belongs to another scope")
    expected_scope = {
        "owner": owner,
        "inputs": loaded["input_manifest"],
        "implementation": implementation,
    }
    if any(
        g["mandate"]["scope"] != expected_scope for g in audit["authoring"]["grants"]
    ) or any(r["scope"] != expected_scope for r in audit["authoring"]["cases"]):
        raise PermissionError(
            "Financial authoring belongs to another owner, inputs or implementation"
        )
    return {
        **audit,
        "output": output,
        "private": api.ui_state_directory(output, create=False),
        "owner": owner,
        "implementation": implementation,
        "packs": info["packs"],
        "revision": api.digest(
            [owner, loaded["run"], loaded["input_manifest"], audit, implementation]
        ),
    }


def registered(loaded: dict, identity: str) -> Path:
    row = next(
        (r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity),
        None,
    )
    if row is None:
        raise PermissionError(
            "Financial Analysis source is outside this registered run"
        )
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if file_hash(path) != row["sha256"]:
        raise ValueError("Financial Analysis registered source bytes changed")
    return path


def selected_case(current: dict, loaded: dict, root: Path, args: dict) -> dict:
    """Only an explicit pack determines the public lexical contract; no semantic inference."""
    pack = args["pack_id"]
    if pack not in current["packs"]:
        raise ValueError("Choose one registered Financial Analysis recipe")
    case = resolve_case(current, loaded, args["case_input_id"])
    authored = next(
        (
            r
            for r in current["authoring"]["cases"]
            if r["case_ref"] == args["case_input_id"]
        ),
        None,
    )
    if authored and authored["pack_id"] != pack:
        raise ValueError("Financial authored case belongs to another recipe")
    if case.suffix.lower() != ".json":
        raise ValueError("Choose the exact registered reviewed JSON case")
    declared = bridge(
        root, {"operation": "bindings", "pack_id": pack, "case": str(case)}
    )
    return {
        "case": case,
        "sources": declared["sources"],
        "case_content": json.loads(case.read_bytes()),
        "case_sha256": file_hash(case),
        **(
            {"reviewed_source_bindings": authored["source_bindings"]}
            if authored
            else {}
        ),
    }


def resolve_case(current: dict, loaded: dict, identity: str) -> Path:
    """An authored case becomes eligible only through its exact named review receipt."""
    if identity.startswith("financial-authored-"):
        from native_financial_authoring import case_path

        return case_path(current, identity)
    return registered(loaded, identity)


def draft(current: dict, loaded: dict, api: Any) -> tuple[Path, dict, str, int]:
    """Generation CAS protects incomplete material choices without approving the case."""
    path = current["private"] / (
        "financial-draft-" + api.digest(current["owner"]) + ".json"
    )
    value = api.read_json(path) if path.exists() else None
    if value and (
        value["owner"] != current["owner"]
        or value["inputs"] != loaded["input_manifest"]
        or value["implementation"] != current["implementation"]
    ):
        raise PermissionError("Financial Analysis draft belongs to another scope")
    return (
        path,
        (
            value["fields"]
            if value
            else {"pack_id": "", "case_input_id": "", "source_bindings": {}}
        ),
        api.digest(value) if value else "",
        value["generation"] if value else 0,
    )


def validate_draft(fields: dict, current: dict, loaded: dict) -> None:
    if not isinstance(fields, dict) or set(fields) != {
        "pack_id",
        "case_input_id",
        "source_bindings",
    }:
        raise ValueError("Invalid Financial Analysis intake fields")
    if any(
        not isinstance(fields[k], str) or len(fields[k]) > 200
        for k in ("pack_id", "case_input_id")
    ):
        raise ValueError("Invalid Financial Analysis intake identity")
    if fields["pack_id"] and fields["pack_id"] not in current["packs"]:
        raise ValueError("Choose a registered Financial Analysis recipe")
    if (
        fields["case_input_id"]
        and resolve_case(current, loaded, fields["case_input_id"]).suffix.lower()
        != ".json"
    ):
        raise ValueError("Choose a registered JSON case")
    values = fields["source_bindings"]
    if not isinstance(values, dict) or any(
        not isinstance(k, str)
        or len(k) > 4000
        or not isinstance(v, str)
        or len(v) > 200
        for k, v in values.items()
    ):
        raise ValueError("Invalid Financial Analysis source bindings")
    for identity in values.values():
        if identity:
            registered(loaded, identity)


def read_version(root: Path, binding: dict, loaded: dict, args: dict, api: Any) -> dict:
    current = context(binding, loaded, root, api)
    row = next(
        (
            v
            for v in current["state"]["versions"]
            if v["source_ref"] == args.get("source_ref")
        ),
        None,
    )
    if row is None:
        raise ValueError("Choose an exact Financial Analysis calculation version")
    directory = current["output"] / row["source_ref"]
    prepared_args = {k: v for k, v in args.items() if k != "source_ref"}
    if args.get("member_ref"):
        prepared_args["source_ref"] = args["member_ref"]
    result = read_prepared(
        root,
        {**loaded, "output_dir": str(directory)},
        prepared_args,
        api.read_json,
        exact_case_path=directory / "case" / "case.json",
    )
    result["revision"] = api.digest([current["revision"], result["revision"], row])
    result["data"]["selection"] = {"source_ref": row["source_ref"]}
    result["data"]["recovery_required"] = current["recovery_required"]
    return result


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    current = context(binding, loaded, root, api)
    action = tool.removeprefix("vera_workspace_financial_")
    if action.startswith("author_"):
        from native_financial_authoring import dispatch as author_dispatch

        return author_dispatch(tool, args, binding, loaded, root, api)
    if action.startswith("source_"):
        from native_financial_sources import dispatch as source_dispatch

        return source_dispatch(tool, args, binding, loaded, root, api)
    if action in {"view", "explain"}:
        result = {
            "work_ref": binding["work_ref"],
            **read_version(root, binding, loaded, args, api),
        }
        if action == "explain":
            if args["revision"] != result["revision"] or result["selection"] is None:
                raise ValueError(
                    "Reopen the exact Financial Analysis artifact and version"
                )
            return {
                "work_ref": binding["work_ref"],
                "source_ref": args["source_ref"],
                "revision": result["revision"],
                "selected": result["selection"],
                "report_ready": False,
                "source_scope": "exact prepared artifact member/page only; named original source requests remain in the maintained workflow",
            }
        return result
    if action == "setup":
        _, fields, stamp, _ = draft(current, loaded, api)
        validate_draft(fields, current, loaded)
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "packs": current["packs"],
            "inputs": [
                {
                    "id": r["binding_id"],
                    "title": Path(r["execution_relative_path"]).name,
                }
                for r in loaded["input_manifest"]["inputs"]
            ]
            + [
                {
                    "id": r["case_ref"],
                    "title": "Caso riesaminato · " + r["pack_id"] + ".json",
                    "authored": True,
                    "pack_id": r["pack_id"],
                }
                for r in current["authoring"]["cases"]
                if r["review"] is not None
                and r["validation"]["valid"]
                and r["review"]["reviewed_case_ref"] == r["case_ref"]
            ],
            "versions": [
                {k: v[k] for k in ("source_ref", "pack_id", "status")}
                for v in current["state"]["versions"]
            ],
            "legacy_pack_available": any(
                (current["output"] / p / "pack_execution_receipt.json").is_file()
                for p in ("", "prepared")
            ),
            "recovery_required": current["recovery_required"],
            "can_write": loaded["run"]["status"] == "running"
            and not current["recovery_required"]
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
            "report_ready": False,
            "draft": fields,
            "draft_revision": stamp,
        }
    if action == "case":
        selected = selected_case(current, loaded, root, args)
        identity = "financial-case-" + api.digest(
            [
                args["pack_id"],
                args["case_input_id"],
                selected["case_sha256"],
                selected["sources"],
            ]
        )
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "selection": {"id": identity},
            "pack_id": args["pack_id"],
            "case_input_id": args["case_input_id"],
            **{k: v for k, v in selected.items() if k != "case"},
            "report_ready": False,
            "professional_approval": False,
        }
    if action == "draft_save":
        if loaded["run"]["status"] != "running" or "REVIEWER" not in os.environ.get(
            "VERA_WORKSPACE_ROLES", ""
        ).split(","):
            raise PermissionError(
                "Financial Analysis drafts require a running reviewer run"
            )
        with api.write_lock(current["output"]):
            loaded = api.load_binding(binding)
            current = context(binding, loaded, root, api)
            if (
                loaded["run"]["status"] != "running"
                or current["recovery_required"]
                or args["revision"] != current["revision"]
            ):
                raise ValueError("Stale or uncertain Financial Analysis draft scope")
            path, _, stamp, generation = draft(current, loaded, api)
            if args["expected_draft_revision"] != stamp:
                raise ValueError("Financial Analysis draft changed in another window")
            validate_draft(args["fields"], current, loaded)
            value = {
                "owner": current["owner"],
                "inputs": loaded["input_manifest"],
                "implementation": current["implementation"],
                "fields": args["fields"],
                "generation": generation + 1,
            }
            api.atomic_json(path, value)
            return {
                "saved": True,
                "draft_revision": api.digest(value),
                "report_ready": False,
                "professional_approval": False,
            }
    if action != "execute":
        raise ValueError("Unknown Financial Analysis native action")
    if loaded["run"]["status"] != "running" or "REVIEWER" not in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(","):
        raise PermissionError(
            "Financial Analysis execution requires an owned running reviewer run"
        )
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid Financial Analysis request key")
    fingerprint = api.digest([tool, current["owner"], args])
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        private = api.ui_state_directory(current["output"])
        intent = private / (
            "financial-request-" + api.digest([current["owner"], key]) + ".json"
        )
        if intent.exists():
            saved = api.read_json(intent)
            if saved["request_sha256"] != fingerprint or "result" not in saved:
                raise ValueError("Different or interrupted Financial Analysis request")
            return saved["result"]
        if (
            current["recovery_required"]
            or args["revision"] != current["revision"]
            or loaded["run"]["status"] != "running"
        ):
            raise ValueError("Stale or uncertain Financial Analysis scope")
        if args["confirmed"] is not True:
            raise ValueError("Explicit reviewed-case execution confirmation required")
        selected = selected_case(current, loaded, root, args)
        expected = "financial-case-" + api.digest(
            [
                args["pack_id"],
                args["case_input_id"],
                selected["case_sha256"],
                selected["sources"],
            ]
        )
        if args["item_id"] != expected:
            raise ValueError("Choose the exact displayed Financial Analysis case")
        bindings = args["source_bindings"]
        if (
            selected.get("reviewed_source_bindings") is not None
            and bindings != selected["reviewed_source_bindings"]
        ):
            raise ValueError(
                "Financial authored execution must preserve the exact professionally reviewed source bindings"
            )
        if not isinstance(bindings, dict) or set(bindings) != {
            r["source_id"] for r in selected["sources"]
        }:
            raise ValueError("Bind every case-declared source explicitly")
        copies = {}
        for source in selected["sources"]:
            locator = source["locator"]
            if locator == "case.json":
                raise ValueError(
                    "Financial Analysis source collides with the reviewed case"
                )
            original = registered(loaded, bindings[source["source_id"]])
            if locator in copies and file_hash(copies[locator]) != file_hash(original):
                raise ValueError("Conflicting Financial Analysis source locators")
            copies[locator] = original
        api.atomic_json(intent, {"request_sha256": fingerprint})
        reference = "financial-" + fingerprint
        directory = current["output"] / reference
        case_dir = directory / "case"
        case_dir.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(selected["case"], case_dir / "case.json")
        for locator, original in copies.items():
            target = case_dir / locator
            target.parent.mkdir(parents=True, exist_ok=True)
            with original.open("rb") as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination)
        result = bridge(
            root,
            {
                "operation": "execute",
                "pack_id": args["pack_id"],
                "case": str(case_dir / "case.json"),
                "context": str(loaded["context_path"]),
                "output": str(directory / "prepared"),
            },
        )
        refreshed = api.load_binding(binding)
        if (
            refreshed["input_manifest"] != loaded["input_manifest"]
            or refreshed["run"]["status"] != "running"
        ):
            raise ValueError("Financial Analysis run changed during execution")
        if (
            context(binding, refreshed, root, api)["implementation"]
            != current["implementation"]
        ):
            raise ValueError(
                "Financial Analysis implementation changed during execution"
            )
        resolve_case(
            context(binding, refreshed, root, api), refreshed, args["case_input_id"]
        )
        for identity in bindings.values():
            registered(refreshed, identity)
        read_prepared(
            root,
            {**loaded, "output_dir": str(directory)},
            {},
            api.read_json,
            exact_case_path=case_dir / "case.json",
        )
        row = {
            "source_ref": reference,
            "pack_id": args["pack_id"],
            "status": result["receipt"]["status"],
            "owner": current["owner"],
            "inputs": loaded["input_manifest"],
            "implementation": current["implementation"],
            "case_input_id": args["case_input_id"],
            "source_bindings": bindings,
            "artifacts": tree_hash(directory),
        }
        api.atomic_json(
            private / "financial-state.json",
            {"versions": [*current["state"]["versions"], row]},
        )
        result = {
            "saved": True,
            "source_ref": reference,
            "pack_id": args["pack_id"],
            "status": row["status"],
            "report_ready": False,
            "professional_approval": False,
            "run_completed": False,
        }
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
