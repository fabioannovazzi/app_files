"""Purpose-bound queries through the public helper, outside sealed Plan revisions."""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["dispatch"]


def query_state(current: dict, binding: dict, api: Any) -> dict:
    """Verify owner isolation and immutable query populations mechanically."""
    owner = owner_scope(binding)
    identity = api.digest(owner)
    state_path = current["private"] / ("sales-query-state-" + identity + ".json")
    saved = (
        api.read_json(state_path)
        if state_path.exists()
        else {"owner": owner, "queries": []}
    )
    if saved["owner"] != owner:
        raise PermissionError("Sales query belongs to another owner")
    prefix = "sales-query-" + identity + "-"
    known = set()
    for row in saved["queries"]:
        name = row["query_ref"]
        if not re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}", name) or name in known:
            raise ValueError("Invalid Sales query identity")
        known.add(name)
        if tree_hash(current["output"] / name) != row["artifacts"]:
            raise ValueError("Sales query artifact bytes or population changed")
    interrupted = any(
        "result" not in api.read_json(path)
        for path in current["private"].glob(
            "sales-query-request-" + identity + "-*.json"
        )
    )
    orphan = any(
        path.name not in known for path in current["output"].glob(prefix + "*")
    )
    return {
        "path": state_path,
        "saved": saved,
        "prefix": prefix,
        "owner_id": identity,
        "recovery_required": interrupted or orphan,
    }


def selected_plan(
    args: dict, binding: dict, loaded: dict, root: Path, api: Any, current: dict
) -> tuple[dict, dict]:
    """Require the exact retained revision, including its original source replay."""
    from native_sales_plan import read_prepared

    prepared = read_prepared(
        root, binding, loaded, {"source_ref": args["source_ref"]}, api
    )
    if args["revision"] != prepared["revision"]:
        raise ValueError("Stale Sales scenario revision")
    record = next(
        row
        for row in current["saved"]["generations"]
        if row["generation"] == args["source_ref"]
    )
    return prepared, record


def query_page(record: dict, args: dict, current: dict, api: Any) -> dict:
    """Render a page; model discussion receives all matches or a truthful refusal."""
    from native_sales_plan import page_offset

    directory = current["output"] / record["query_ref"]
    request = api.read_json(directory / "request.json")
    base = {
        "work_ref": args["work_ref"],
        "revision": args["revision"],
        "query_ref": record["query_ref"],
        "source_ref": record["source_ref"],
        "status": record["status"],
        "request": request,
    }
    if record["status"] != "queried":
        return {**base, "error": api.read_json(directory / "refusal.json")["error"]}
    evidence = api.read_json(directory / record["artifact"])
    if args.get("explain"):
        result = {
            **base,
            "untrusted_source_evidence": True,
            "professional_approval": False,
            "report_ready": False,
            "evidence": evidence,
        }
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 65536:
            raise ValueError(
                "All exact matches exceed the model context limit; refine filters or columns in a new query. No sample was returned"
            )
    else:
        offset = page_offset(args)
        result = {
            **base,
            "columns": evidence["columns"],
            "rows": evidence["rows"][offset : offset + 20],
            "offset": offset,
            "total": evidence["matched_row_count"],
            "has_more": offset + 20 < evidence["matched_row_count"],
            "population_rows_scanned": evidence["full_population_rows_scanned_locally"],
            "match_behavior": evidence["match_behavior"],
        }
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 100000:
            raise ValueError(
                "Scenario page exceeds the private UI limit; refine columns in a new query. All matches remain retained locally"
            )
    if tree_hash(directory) != record["artifacts"]:
        raise ValueError("Sales query changed during reading")
    return result


def dispatch(
    tool: str,
    args: dict,
    binding: dict,
    loaded: dict,
    root: Path,
    api: Any,
    current: dict,
) -> dict:
    """Retain unchanged helper results with intent, exact-scope retries and no approval."""
    from native_sales_plan import context, engine_call, page_offset

    prepared, plan = selected_plan(args, binding, loaded, root, api, current)
    store = query_state(current, binding, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_sales_plan_query_setup":
        directory = current["output"] / args["source_ref"] / "plan"
        manifest = directory / "model_use_manifest.json"
        headers = []
        if manifest.exists():
            with (directory / "sales_plan_scenario.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                headers = next(csv.reader(stream))
        if tree_hash(directory.parent) != plan["artifacts"]:
            raise ValueError("Sales scenario changed during inspection")
        contract = engine_call(root, {"operation": "contract"})
        rows = [
            row
            for row in store["saved"]["queries"]
            if row["source_ref"] == args["source_ref"]
        ]
        offset = page_offset(args)
        return {
            "work_ref": args["work_ref"],
            "revision": prepared["revision"],
            "data": {"selection": {"source_ref": args["source_ref"]}},
            "status": "recovery_required" if store["recovery_required"] else "ready",
            "can_query": writable
            and manifest.exists()
            and not store["recovery_required"],
            "columns": headers,
            "scenarios": {
                "actual": contract["source_scenario"],
                "plan": contract["target_scenario"],
            },
            "items": [
                {key: row[key] for key in ("query_ref", "status")}
                for row in rows[offset : offset + 30]
            ],
            "total": len(rows),
            "has_more": offset + 30 < len(rows),
        }
    if tool in {
        "vera_workspace_sales_plan_query_read",
        "vera_workspace_sales_plan_query_explain",
    }:
        record = next(
            (
                row
                for row in store["saved"]["queries"]
                if row["query_ref"] == args["query_ref"]
                and row["source_ref"] == args["source_ref"]
            ),
            None,
        )
        if record is None:
            raise PermissionError(
                "Sales query is outside this actor, run or exact Plan revision"
            )
        return query_page(
            record, {**args, "explain": tool.endswith("_explain")}, current, api
        )
    if tool != "vera_workspace_sales_plan_query":
        raise ValueError("Unknown Sales scenario query action")
    if not writable:
        raise PermissionError(
            "A running Sales Plan run and reviewer authority are required for a retained query"
        )
    if args.get("human_reviewed") is not True:
        raise ValueError("Confirm the exact query purpose, selectors and columns")
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid Sales query request key")
    fingerprint = api.digest(
        [tool, owner_scope(binding), binding, args, current["implementation"]]
    )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        if loaded["run"]["status"] != "running":
            raise PermissionError("Sales query run is no longer running")
        current = context(binding, loaded, root, api)
        selected_plan(args, binding, loaded, root, api, current)
        store = query_state(current, binding, api)
        intent = current["private"] / (
            "sales-query-request-" + store["owner_id"] + "-" + api.digest(key) + ".json"
        )
        if intent.exists():
            previous = api.read_json(intent)
            if previous["request_sha256"] != fingerprint:
                raise ValueError("Sales query key belongs to a different request")
            if "result" not in previous:
                raise ValueError("Interrupted Sales query requires specialist recovery")
            return previous["result"]
        if store["recovery_required"] or current["recovery_required"]:
            raise ValueError(
                "Existing Sales outputs or queries require specialist recovery"
            )
        query_ref = store["prefix"] + fingerprint
        directory = current["output"] / query_ref
        api.atomic_json(intent, {"request_sha256": fingerprint})
        directory.mkdir()
        source = current["output"] / args["source_ref"] / "plan"
        # The public helper requires colocated sealed evidence and retains every
        # match. Exact copies in a new query tree leave the Plan seal unchanged.
        for name in ("model_use_manifest.json", "sales_plan_scenario.csv"):
            (directory / name).write_bytes((source / name).read_bytes())
        request = {
            key: args[key] for key in ("reason", "source_row_ids", "where", "columns")
        }
        api.atomic_json(directory / "request.json", request)
        result = engine_call(
            root,
            {
                "operation": "query",
                "manifest": str(directory / "model_use_manifest.json"),
                "context": str(loaded["context_path"]),
                **request,
            },
        )
        api.load_binding(binding)
        if (
            engine_call(root, {"operation": "implementation"})
            != current["implementation"]
            or tree_hash(source.parent) != plan["artifacts"]
        ):
            raise ValueError(
                "Sales Plan implementation or scenario changed during query"
            )
        for name in ("model_use_manifest.json", "sales_plan_scenario.csv"):
            if file_hash(directory / name) != file_hash(source / name):
                raise ValueError("Sales query copy differs from the sealed Plan")
        record = {
            "query_ref": query_ref,
            "source_ref": args["source_ref"],
            "status": "queried" if result["ok"] else "invalid_query",
        }
        if result["ok"]:
            artifact = Path(result["artifact_path"])
            if artifact.parent != directory / "model_drilldowns" or not re.fullmatch(
                r"scenario_rows_[0-9a-f]{24}\.json", artifact.name
            ):
                raise ValueError("Sales helper returned an unexpected artifact")
            record["artifact"] = artifact.relative_to(directory).as_posix()
        else:
            api.atomic_json(directory / "refusal.json", result)
        record["artifacts"] = tree_hash(directory)
        store["saved"]["queries"].append(record)
        api.atomic_json(store["path"], store["saved"])
        receipt = {
            "saved": True,
            "status": record["status"],
            "query_ref": query_ref,
            "source_ref": args["source_ref"],
            "professional_approval": False,
            "report_ready": False,
            "run_completed": False,
        }
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": receipt})
        return receipt
