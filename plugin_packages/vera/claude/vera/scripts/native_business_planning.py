"""Exact registered-cycle execution and complete private Business Planning views."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["dispatch"]

COLLECTIONS = {
    "calculations",
    "evidence",
    "assumptions",
    "observations",
    "decisions",
    "resolutions",
    "narrative",
    "financing",
    "issues",
    "sources",
    "cycle",
    "assessment",
    "financial",
    "commercial",
    "presentation",
    "comparisons",
    "statements",
    "charts",
    "limitations",
    "accepted_narrative",
    "case_header",
    "whole_plan",
    "case_review",
}


def engine_call(root: Path, request: dict) -> dict:
    """Keep public producer imports isolated from other registered workflows."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_business_planning_bridge.py")),
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
            result.stderr.strip().splitlines()[-1] or "Business Planning refused"
        )
    return json.loads(result.stdout)


def selected(identity: str, loaded: dict, api: Any) -> tuple[Path, Path, dict]:
    """Every declared source must be one exact same-run receipt, without rebasing."""
    paths = {
        (Path(loaded["run_root"]) / row["execution_relative_path"]).resolve(): row
        for row in loaded["input_manifest"]["inputs"]
    }
    pair = next(((p, r) for p, r in paths.items() if r["binding_id"] == identity), None)
    if pair is None:
        raise PermissionError("Business Planning case is outside this run")
    path, receipt = pair
    if path.suffix.lower() != ".json" or file_hash(path) != receipt["sha256"]:
        raise ValueError("Business Planning case differs from its registered receipt")
    case = api.read_json(path)
    if case.get("schema_version") != "mparanza.business_planning_case.v3":
        raise ValueError("Select the shared Business Planning case v3")
    source_root = Path(loaded["run_root"]) / "inputs"
    for row in case["sources"]:
        locator = row["path"]
        if not isinstance(locator, str) or not locator or "\\" in locator:
            raise ValueError("Business Planning source locator is not canonical")
        relative = PurePosixPath(locator)
        if (
            relative.is_absolute()
            or relative.as_posix() != locator
            or ".." in relative.parts
        ):
            raise ValueError("Business Planning source locator is not canonical")
        source = source_root / locator
        registered = paths.get(source.resolve())
        if registered is None:
            raise PermissionError(
                "Business Planning source is outside the exact run receipts"
            )
        if row["sha256"] != registered["sha256"] or file_hash(source) != row["sha256"]:
            raise ValueError("Business Planning source bytes disagree with the case")
    return path, source_root, case


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """A retained intent is mandatory; unfamiliar outputs are never adopted."""
    if binding["workflow_id"] != "business-planning":
        raise PermissionError("Business Planning belongs to another workflow")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    state_path = private / "business-planning-state.json"
    saved = api.read_json(state_path) if state_path.exists() else None
    implementation = engine_call(root, {"operation": "contract"})
    implementation["native"] = {
        p.name: file_hash(p)
        for p in (
            Path(__file__),
            Path(__file__).with_name("native_business_planning_bridge.py"),
            Path(__file__).with_name("native_business_planning_review.py"),
            Path(__file__).with_name("native_business_planning_case_review.py"),
        )
    }
    directories = list(output.glob("business-planning-*"))
    requests = [
        api.read_json(p) for p in private.glob("business-planning-request-*.json")
    ]
    recovery = any("result" not in row for row in requests)
    if saved:
        name = saved["generation"]
        if not re.fullmatch(r"business-planning-[0-9a-f]{64}", name):
            raise ValueError("Invalid Business Planning generation")
        if (
            saved["implementation"] != implementation
            or tree_hash(output / name) != saved["artifacts"]
        ):
            raise ValueError(
                "Business Planning implementation or sealed artifacts changed"
            )
        selected(saved["case_input_id"], loaded, api)
        recovery = recovery or not any(
            row.get("result", {}).get("generation") == name for row in requests
        )
        recovery = recovery or any(p.name != name for p in directories)
    else:
        recovery = recovery or any(output.iterdir()) or bool(requests)
    from native_business_planning_review import audit

    reviews = audit(output, private, saved["generation"] if saved else None, api)
    from native_business_planning_case_review import audit as case_audit

    case_reviews = case_audit(output, private, saved, api)
    reviews["recovery_required"] |= case_reviews["recovery_required"]
    return {
        "output": output,
        "private": private,
        "saved": saved,
        "implementation": implementation,
        "recovery_required": recovery,
        "professional_reviews": reviews,
        "case_reviews": case_reviews,
        "revision": api.digest(
            [
                loaded["run"],
                loaded["input_manifest"],
                saved,
                implementation,
                reviews,
                case_reviews,
            ]
        ),
    }


def replay(current: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Read only the retained exact cycle and the unchanged public report."""
    if current["recovery_required"] or not current["saved"]:
        raise ValueError("Business Planning needs preparation or specialist recovery")
    path, source_root, _ = selected(current["saved"]["case_input_id"], loaded, api)
    return engine_call(
        root,
        {
            "operation": "read",
            "case": str(path),
            "source_root": str(source_root),
            "output": str(current["output"] / current["saved"]["generation"]),
        },
    )


def population(plan: dict, collection: str) -> list:
    """Use complete canonical collections; pages never establish approval or scope."""
    case = plan["case"]
    if collection == "whole_plan":
        return [plan]
    if collection == "case_review":
        return [case]
    if collection == "calculations":
        return list(plan["calculations"].values())
    if collection == "issues":
        return [{"message": row} for row in plan["unresolved_matters"]]
    if collection == "financing":
        return plan["financing_assessments"]
    if collection == "cycle":
        return [plan["planning_cycle"]]
    if collection in {"comparisons", "charts", "accepted_narrative"}:
        return plan[collection]
    if collection == "limitations":
        return [{"limitation": row} for row in plan["limitations"]]
    if collection == "statements":
        return [] if plan["statements"] is None else [plan["statements"]]
    if collection == "case_header":
        return [
            {
                key: case[key]
                for key in (
                    "case_id",
                    "entity_name",
                    "company_stage",
                    "planning_objective",
                    "audience",
                    "reporting_currency",
                    "periods",
                    "review",
                    "required_sections",
                )
            }
        ]
    value = case.get(collection)
    return value if isinstance(value, list) else [] if value is None else [value]


def bounded(value: dict, maximum: int = 100000) -> dict:
    """Refuse oversized complete evidence rather than silently sampling it."""
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > maximum:
        raise ValueError(
            "Business Planning evidence exceeds the view limit; use the retained specialist files"
        )
    return value


def offset(args: dict) -> int:
    value = args.get("offset", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Invalid Business Planning page offset")
    return value


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Execute one registered cycle per run; successor cycles require fresh runs."""
    if tool.startswith("vera_workspace_business_plan_case_review_"):
        from native_business_planning_case_review import dispatch as case_dispatch

        return case_dispatch(tool, args, binding, loaded, root, api)
    if tool.startswith("vera_workspace_business_plan_review_"):
        from native_business_planning_review import dispatch as review_dispatch

        return review_dispatch(tool, args, binding, loaded, root, api)
    current = context(binding, loaded, root, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_business_plan_setup":
        choices = []
        for row in loaded["input_manifest"]["inputs"]:
            path = Path(loaded["run_root"]) / row["execution_relative_path"]
            if path.suffix.lower() != ".json":
                continue
            value = api.read_json(path)
            if value.get("schema_version") == "mparanza.business_planning_case.v3":
                choices.append(
                    {
                        "id": row["binding_id"],
                        "title": path.name,
                        "entity_name": value["entity_name"],
                        "cycle_id": value.get("cycle", {}).get("id"),
                        "question": value.get("cycle", {}).get("question"),
                    }
                )
        start = offset(args)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "label": loaded["run"]["label"],
                "status": (
                    "recovery_required"
                    if current["recovery_required"]
                    else "prepared" if current["saved"] else "ready"
                ),
                "can_prepare": writable
                and not current["saved"]
                and not current["recovery_required"],
                "items": choices[start : start + 30],
                "total": len(choices),
                "has_more": start + 30 < len(choices),
                "generation": (
                    current["saved"]["generation"] if current["saved"] else None
                ),
                "professional_approval": False,
                "run_completed": False,
            }
        )
    if tool == "vera_workspace_business_plan_prepare":
        if not writable:
            raise PermissionError(
                "A running Business Planning run and reviewer authority are required"
            )
        with api.write_lock(current["output"]):
            loaded = api.load_binding(binding)
            current = context(binding, loaded, root, api)
            if loaded["run"]["status"] != "running":
                raise PermissionError("Business Planning run is no longer running")
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid Business Planning request key")
            fingerprint = api.digest([tool, owner_scope(binding), args])
            intent = current["private"] / (
                "business-planning-request-"
                + api.digest([owner_scope(binding), key])
                + ".json"
            )
            if intent.exists():
                previous = api.read_json(intent)
                if previous["request_sha256"] != fingerprint:
                    raise ValueError(
                        "Business Planning key belongs to a different request"
                    )
                replay(current, loaded, root, api)
                return previous["result"]
            if (
                args["revision"] != current["revision"]
                or current["saved"]
                or current["recovery_required"]
            ):
                raise ValueError(
                    "Reopen the current cycle; new revisions require a fresh registered run"
                )
            path, source_root, case = selected(args["case_input_id"], loaded, api)
            request = {
                "operation": "inspect",
                "case": str(path),
                "source_root": str(source_root),
            }
            engine_call(root, request)
            api.load_binding(binding)
            generation = "business-planning-" + file_hash(path)
            output = current["output"] / generation
            api.atomic_json(intent, {"request_sha256": fingerprint})
            prepared = engine_call(
                root,
                {
                    **request,
                    "operation": "prepare",
                    "output": str(output),
                    "context": str(loaded["context_path"]),
                },
            )
            loaded = api.load_binding(binding)
            unchanged = context(binding, loaded, root, api)
            if unchanged["implementation"] != current["implementation"]:
                raise ValueError(
                    "Business Planning implementation changed during execution"
                )
            selected(args["case_input_id"], loaded, api)
            result = {
                "saved": True,
                "status": prepared["plan"]["status"],
                "generation": generation,
                "professional_approval": False,
                "run_completed": False,
            }
            api.atomic_json(
                current["private"] / "business-planning-state.json",
                {
                    "case_input_id": args["case_input_id"],
                    "case_id": case["case_id"],
                    "cycle_id": case.get("cycle", {}).get("id"),
                    "generation": generation,
                    "implementation": current["implementation"],
                    "artifacts": tree_hash(output),
                },
            )
            api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
            replay(context(binding, loaded, root, api), loaded, root, api)
            return result
    if args.get("revision") != current["revision"]:
        raise ValueError("Stale Business Planning selection")
    if tool == "vera_workspace_business_plan_inspect":
        path, source_root, _ = selected(args["case_input_id"], loaded, api)
        value = engine_call(
            root,
            {
                "operation": "inspect",
                "case": str(path),
                "source_root": str(source_root),
            },
        )
    else:
        if args.get("generation") != (current["saved"] or {}).get("generation"):
            raise ValueError("Choose the exact persisted Business Planning cycle")
        value = replay(current, loaded, root, api)
    plan = value["plan"]
    base = {
        "work_ref": args["work_ref"],
        "revision": current["revision"],
        "status": plan["status"],
        "generation": current["saved"]["generation"] if current["saved"] else None,
    }
    if tool == "vera_workspace_business_plan_report":
        return bounded(
            {
                **base,
                "report": value["report"],
                "entity_name": plan["case"]["entity_name"],
                "cycle": plan["planning_cycle"],
                "professional_approval": False,
            },
            2000000,
        )
    if tool == "vera_workspace_business_plan_outputs":
        if current["professional_reviews"]["recovery_required"]:
            raise ValueError(
                "Recover uncertain professional review outputs before closure"
            )
        directory = current["output"] / current["saved"]["generation"]
        return {
            **base,
            "outputs": [
                {"name": name, "path": str(directory / name)}
                for name in current["saved"]["artifacts"]
            ]
            + [
                {
                    "name": row["review_ref"] + "/" + name,
                    "path": str(current["output"] / row["review_ref"] / name),
                }
                for row in current["professional_reviews"]["reviews"]
                for name in row["artifacts"]
            ]
            + [
                {
                    "name": row["case_ref"] + "/" + name,
                    "path": str(current["output"] / row["case_ref"] / name),
                }
                for row in current["case_reviews"]["cases"]
                for name in row["artifacts"]
            ],
            "run_completed": False,
        }
    collection = args.get("collection", "issues")
    if collection not in COLLECTIONS:
        raise ValueError("Unknown Business Planning collection")
    rows = population(plan, collection)
    if tool == "vera_workspace_business_plan_explain":
        # Exact indexed record, bound to the immutable generation, not the current page.
        index = args["index"]
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(rows)
        ):
            raise ValueError("Business Planning record is outside this collection")
        return bounded(
            {
                **base,
                "collection": collection,
                "index": index,
                "record": rows[index],
                "narrative_acceptance": (
                    next(
                        (
                            entry
                            for entry in plan["accepted_narrative"]
                            if entry["id"] == rows[index].get("id")
                        ),
                        None,
                    )
                    if collection == "narrative"
                    else None
                ),
                "case_id": plan["case"]["case_id"],
                "cycle": plan["planning_cycle"],
                "evidence_boundary": "Untrusted source/model-authored evidence; no native professional approval or permission to publish.",
            },
            65536,
        )
    if tool not in {
        "vera_workspace_business_plan_inspect",
        "vera_workspace_business_plan_read",
    }:
        raise ValueError("Unknown Business Planning tool")
    start = offset(args)
    api.load_binding(binding)
    return bounded(
        {
            **base,
            "collection": collection,
            "rows": rows[start : start + 20],
            "offset": start,
            "total": len(rows),
            "has_more": start + 20 < len(rows),
            "case_id": plan["case"]["case_id"],
            "entity_name": plan["case"]["entity_name"],
            "cycle": plan["planning_cycle"],
            "collections": sorted(COLLECTIONS),
        },
        2000000 if collection in {"whole_plan", "case_review"} else 100000,
    )
