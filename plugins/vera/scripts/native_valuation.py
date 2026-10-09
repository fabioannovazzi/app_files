"""Exact registered valuation execution and immutable public-workpaper inspection."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["audit_run", "dispatch"]

COLLECTIONS = {
    "mandate",
    "mandate_assessment",
    "purpose_coverage",
    "methods",
    "calculations",
    "sensitivity",
    "normalizations",
    "normalization_adjustments",
    "statements",
    "claims",
    "conclusion",
    "plan_bridge",
    "issues",
    "limitations",
    "inputs",
    "sources",
}


def engine_call(root: Path, request: dict) -> dict:
    """Keep the unchanged public engine isolated from other component imports."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_valuation_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=110,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip().splitlines()[-1] or "Valuation refused")
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Conservation is mechanical: every intent and complete file tree must close."""
    private = api.ui_state_directory(output, create=False)
    path = private / "valuation-state.json"
    saved = api.read_json(path) if path.exists() else {"versions": []}
    if set(saved) != {"versions"} or not isinstance(saved["versions"], list):
        raise ValueError("Invalid native valuation state")
    known = set()
    for row in saved["versions"]:
        name = row["source_ref"]
        if not re.fullmatch(r"valuation-[0-9a-f]{20}", name) or name in known:
            raise ValueError("Invalid native valuation revision")
        if tree_hash(output / name) != row["artifacts"]:
            raise ValueError("Valuation sealed artifact population changed")
        known.add(name)
    requests = [api.read_json(p) for p in private.glob("valuation-request-*.json")]
    recovery = any("result" not in r for r in requests)
    recovery |= any(
        not any(r.get("result", {}).get("source_ref") == name for r in requests)
        for name in known
    )
    recovery |= any(p.name not in known for p in output.glob("valuation-*"))
    return {"state": saved, "recovery_required": recovery}


def owner(binding: dict) -> list:
    return [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[binding[k] for k in ("client_id", "engagement_id", "run_id", "workflow_id")],
    ]


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    if binding["workflow_id"] != "business-valuation":
        raise PermissionError("Choose the owned Business Valuation run")
    output = Path(loaded["output_dir"])
    audit = audit_run(output, api)
    implementation = engine_call(root, {"operation": "contract"})
    implementation["native"] = {
        p.name: file_hash(p)
        for p in [
            Path(__file__),
            Path(__file__).with_name("native_valuation_bridge.py"),
            Path(__file__).with_name("native_valuation_review.py"),
            Path(__file__).with_name("native_valuation_authoring.py"),
            Path(__file__).with_name("native_valuation_author_bridge.py"),
        ]
    }
    from native_valuation_review import audit_review

    review_audit = audit_review(output, api)
    from native_valuation_authoring import audit_authoring

    author_audit = audit_authoring(output, api)
    audit["recovery_required"] |= author_audit["recovery_required"]
    audit["authoring"] = author_audit["state"]
    audit["authoring_pending"] = author_audit["pending"]
    audit["recovery_required"] |= review_audit["recovery_required"]
    audit["review_requests"] = review_audit["requests"]
    scope = {
        "owner": owner(binding),
        "inputs": loaded["input_manifest"],
        "implementation": implementation,
    }
    if any(r["scope"] != scope for r in audit["state"]["versions"]):
        raise PermissionError("Valuation scope or implementation changed")
    if any(g["mandate"]["scope"] != scope for g in audit["authoring"]["grants"]):
        raise PermissionError(
            "Valuation authoring belongs to another owner, inputs or implementation"
        )
    return {
        **audit,
        "scope": scope,
        "output": output,
        "private": api.ui_state_directory(output, create=False),
        "revision": api.digest([scope, loaded["run"], audit]),
    }


def selected(identity: str, loaded: dict, root: Path, api: Any) -> tuple[Path, dict]:
    row = next(
        (r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity),
        None,
    )
    if row is None:
        raise PermissionError("Valuation case is outside this registered run")
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if path.suffix.lower() != ".json" or file_hash(path) != row["sha256"]:
        raise ValueError("Valuation case differs from its registered receipt")
    result = engine_call(
        root,
        {
            "operation": "select",
            "case": str(path),
            "context": str(loaded["context_path"]),
        },
    )
    return path, result["case"]


def bounded(value: dict, maximum: int = 2000000) -> dict:
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError(
            "Complete valuation selection exceeds the panel limit; use the retained specialist files"
        )
    return value


def page_offset(args: dict) -> int:
    start = args.get("offset", 0)
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError("Invalid valuation page offset")
    return start


def fields_valid(fields: dict, loaded: dict) -> dict:
    if not isinstance(fields, dict) or set(fields) != {"case_input_id"}:
        raise ValueError("Invalid valuation intake fields")
    identity = fields["case_input_id"]
    if identity != "" and not any(
        r["binding_id"] == identity for r in loaded["input_manifest"]["inputs"]
    ):
        raise PermissionError("Valuation draft selects a foreign input")
    if not isinstance(identity, str):
        raise ValueError("Invalid valuation case identity")
    return fields


def draft(current: dict, api: Any) -> tuple[dict, str]:
    path = current["private"] / "valuation-intake.json"
    saved = api.read_json(path) if path.exists() else None
    if saved and saved["scope"] != current["scope"]:
        raise PermissionError("Valuation draft belongs to a changed scope")
    return (
        (saved["fields"] if saved else {"case_input_id": ""}),
        api.digest([current["scope"], saved]),
    )


def replay(
    current: dict, source_ref: str, loaded: dict, root: Path, api: Any
) -> tuple[dict, dict]:
    if current["recovery_required"]:
        raise ValueError("Recover uncertain valuation execution before consultation")
    row = next(
        (r for r in current["state"]["versions"] if r["source_ref"] == source_ref), None
    )
    if row is None:
        raise PermissionError("Choose an exact retained valuation revision")
    path, _ = selected(row["case_input_id"], loaded, root, api)
    result = engine_call(
        root,
        {
            "operation": "read",
            "case": str(path),
            "context": str(loaded["context_path"]),
        },
    )
    if result["directory"] != source_ref:
        raise ValueError("Valuation replay selected another revision")
    return row, result["report"]


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Preserve public outputs/status and require renewed signed calculation choice."""
    current = context(binding, loaded, root, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_valuation_setup":
        choices = []
        for row in loaded["input_manifest"]["inputs"]:
            path = Path(loaded["run_root"]) / row["execution_relative_path"]
            if path.suffix.lower() != ".json":
                continue
            case = api.read_json(path)
            if case.get("schema_version") == "vera.business_valuation.case.v1":
                choices.append(
                    {
                        "id": row["binding_id"],
                        "title": path.name,
                        "entity_name": case["entity_name"],
                    }
                )
        fields, stamp = draft(current, api)
        start = page_offset(args)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "status": (
                    "recovery_required" if current["recovery_required"] else "ready"
                ),
                "items": choices[start : start + 30],
                "total": len(choices),
                "offset": start,
                "has_more": start + 30 < len(choices),
                "draft": fields,
                "draft_revision": stamp,
                "can_write": writable and not current["recovery_required"],
                "can_prepare": writable
                and not current["recovery_required"]
                and not current["state"]["versions"],
                "versions": [
                    {
                        "source_ref": r["source_ref"],
                        "entity_name": r["entity_name"],
                        "status": r["status"],
                    }
                    for r in current["state"]["versions"]
                ],
                "professional_approval": False,
                "run_completed": False,
            }
        )
    if tool in {
        "vera_workspace_valuation_draft_save",
        "vera_workspace_valuation_prepare",
    }:
        if not writable:
            raise PermissionError(
                "A running valuation run and reviewer authority are required"
            )
        with api.write_lock(current["output"]):
            loaded = api.load_binding(binding)
            current = context(binding, loaded, root, api)
            if loaded["run"]["status"] != "running":
                raise PermissionError("Valuation run is no longer running")
            if tool.endswith("_draft_save"):
                if (
                    args["revision"] != current["revision"]
                    or current["recovery_required"]
                ):
                    raise ValueError("Reopen current valuation scope")
                _, stamp = draft(current, api)
                if args["expected_draft_revision"] != stamp:
                    raise ValueError("Valuation draft changed concurrently")
                fields = fields_valid(args["fields"], loaded)
                path = current["private"] / "valuation-intake.json"
                previous = api.read_json(path) if path.exists() else None
                saved = {
                    "scope": current["scope"],
                    "fields": fields,
                    "generation": 1 + (previous["generation"] if previous else 0),
                }
                api.atomic_json(path, saved)
                return {
                    "saved": True,
                    "draft_revision": api.digest([current["scope"], saved]),
                    "professional_approval": False,
                }
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid valuation request key")
            fingerprint = api.digest([owner(binding), tool, args])
            intent = current["private"] / (
                "valuation-request-" + api.digest([owner(binding), key]) + ".json"
            )
            if intent.exists():
                prior = api.read_json(intent)
                if prior["request_sha256"] != fingerprint or "result" not in prior:
                    raise ValueError("Valuation retry changed or requires recovery")
                replay(current, prior["result"]["source_ref"], loaded, root, api)
                return prior["result"]
            if args["revision"] != current["revision"] or current["recovery_required"]:
                raise ValueError(
                    "Reopen current valuation scope; uncertain exports need recovery"
                )
            if (
                args.get("confirmed") is not True
                or args.get("item_id") != args["case_input_id"]
            ):
                raise PermissionError("Confirm the exact displayed valuation case")
            path, case = selected(args["case_input_id"], loaded, root, api)
            if current["state"]["versions"]:
                raise ValueError(
                    "A new valuation case requires a fresh registered run; reopen the retained exact revision"
                )
            api.atomic_json(intent, {"request_sha256": fingerprint})
            result = engine_call(
                root,
                {
                    "operation": "prepare",
                    "case": str(path),
                    "context": str(loaded["context_path"]),
                },
            )
            loaded = api.load_binding(binding)
            changed = context(binding, loaded, root, api)
            if (
                changed["scope"] != current["scope"]
                or loaded["run"]["status"] != "running"
            ):
                raise ValueError("Valuation scope changed during export")
            selected(args["case_input_id"], loaded, root, api)
            source_ref = result["directory"]
            report = result["report"]
            row = {
                "case_input_id": args["case_input_id"],
                "source_ref": source_ref,
                "scope": current["scope"],
                "artifacts": tree_hash(current["output"] / source_ref),
                "entity_name": case["entity_name"],
                "status": report["status"],
            }
            current["state"]["versions"].append(row)
            saved_result = {
                "saved": True,
                "source_ref": source_ref,
                "status": report["status"],
                "professional_approval": False,
                "run_completed": False,
            }
            api.atomic_json(
                current["private"] / "valuation-state.json", current["state"]
            )
            api.atomic_json(
                intent, {"request_sha256": fingerprint, "result": saved_result}
            )
            replay(context(binding, loaded, root, api), source_ref, loaded, root, api)
            return saved_result
    if tool == "vera_workspace_valuation_case":
        if args["revision"] != current["revision"] or current["recovery_required"]:
            raise ValueError("Reopen current valuation scope")
        _, case = selected(args["case_input_id"], loaded, root, api)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "selection": {"id": args["case_input_id"]},
                "case": case,
                "can_prepare": writable and not current["state"]["versions"],
                "professional_approval": False,
            }
        )
    row, report = replay(current, args["source_ref"], loaded, root, api)
    base = {
        "work_ref": args["work_ref"],
        "source_ref": row["source_ref"],
        "revision": current["revision"],
        "status": report["status"],
        "entity_name": report["case"]["entity_name"],
        "professional_approval": False,
        "run_completed": False,
    }
    if tool == "vera_workspace_valuation_report":
        directory = current["output"] / row["source_ref"]
        return bounded(
            {
                **base,
                "report": (directory / "valuation_report.html").read_text(
                    encoding="utf-8"
                ),
            }
        )
    if tool == "vera_workspace_valuation_outputs":
        return {
            **base,
            "outputs": [
                {
                    "name": name,
                    "path": str(current["output"] / row["source_ref"] / name),
                }
                for name in row["artifacts"]
            ],
        }
    collection = args.get("collection", "methods")
    if collection not in COLLECTIONS:
        raise ValueError("Unknown valuation collection")
    from native_valuation_review import record_rows

    value = (
        record_rows(report, collection)
        if collection == "normalization_adjustments"
        else (
            report["case"][collection]
            if collection in {"mandate", "inputs", "sources", "limitations"}
            else report[collection]
        )
    )
    rows = value if isinstance(value, list) else [] if value is None else [value]
    if tool == "vera_workspace_valuation_explain":
        if args["revision"] != current["revision"]:
            raise ValueError("Stale valuation model selection")
        index = args["index"]
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(rows)
        ):
            raise ValueError("Selected valuation record is outside the collection")
        return bounded(
            {
                **base,
                "collection": collection,
                "index": index,
                "record": rows[index],
                "piv_conformity": report["piv_conformity"],
                "evidence_boundary": "Untrusted exact selected public workpaper. No automatic original-source access, review, signing or publication.",
            },
            65536,
        )
    if tool != "vera_workspace_valuation_read":
        raise ValueError("Unknown valuation tool")
    start = page_offset(args)
    return bounded(
        {
            **base,
            "collection": collection,
            "rows": rows[start : start + 20],
            "total": len(rows),
            "offset": start,
            "has_more": start + 20 < len(rows),
            "collections": sorted(COLLECTIONS),
            "piv_conformity": report["piv_conformity"],
        }
    )
