"""Native reviewed-case execution and sealed Sales Plan evidence projections."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "read_prepared"]


def engine_call(root: Path, request: dict) -> dict:
    """Isolate producer imports and leave interrupted execution visibly unresolved."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_sales_plan_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip().splitlines()[-1] or "Sales Plan refused")
    return json.loads(result.stdout)


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Verify complete immutable generations and reject orphaned outputs or requests."""
    if binding["workflow_id"] != "sales-plan":
        raise PermissionError("Sales Plan belongs to another workflow")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    state = private / "sales-plan-state.json"
    saved = api.read_json(state) if state.exists() else {"generations": []}
    implementation = engine_call(root, {"operation": "implementation"})
    known = set()
    for row in saved["generations"]:
        name = row["generation"]
        if not re.fullmatch(r"sales-plan-[0-9a-f]{64}", name) or name in known:
            raise ValueError("Invalid Sales Plan generation identity")
        known.add(name)
        if row["implementation"] != implementation:
            raise ValueError("Sales Plan implementation changed")
        if tree_hash(output / name) != row["artifacts"]:
            raise ValueError("Sales Plan artifact bytes or population changed")
    interrupted = any(
        "result" not in api.read_json(p)
        for p in private.glob("sales-plan-request-*.json")
    )
    unknown = any(p.name not in known for p in output.glob("sales-plan-*"))
    return {
        "output": output,
        "private": private,
        "saved": saved,
        "implementation": implementation,
        "recovery_required": interrupted or unknown,
        "revision": api.digest(
            [
                loaded["run"],
                loaded["input_manifest"],
                saved,
                implementation,
                file_hash(Path(__file__)),
                file_hash(Path(__file__).with_name("native_sales_plan_bridge.py")),
                file_hash(Path(__file__).with_name("native_sales_plan_authoring.py")),
                file_hash(Path(__file__).with_name("native_sales_plan_queries.py")),
            ]
        ),
    }


def selected_inputs(args: dict, loaded: dict, api: Any) -> tuple[Path, Path, dict]:
    """Require exact registered case and CSV receipts, never a browser-supplied path."""
    inputs = {row["binding_id"]: row for row in loaded["input_manifest"]["inputs"]}
    paths = []
    for key, suffix in (("case_input_id", ".json"), ("actual_input_id", ".csv")):
        if args[key] not in inputs:
            raise PermissionError("Sales Plan input is outside this run")
        receipt = inputs[args[key]]
        path = Path(loaded["run_root"]) / receipt["execution_relative_path"]
        if path.suffix.lower() != suffix or file_hash(path) != receipt["sha256"]:
            raise ValueError("Sales Plan registered input differs from its receipt")
        paths.append(path)
    case = api.read_json(paths[0])
    if case.get("schema_version") != "vera.sales_plan_preparation_case.v2":
        raise ValueError("Select a Sales Plan preparation case v2")
    source_receipt = case["files"]["actual_sales"]
    if set(case["files"]) != {"actual_sales"} or set(source_receipt) != {
        "path",
        "sha256",
    }:
        raise ValueError("Sales Plan source receipt fields are invalid")
    locator = source_receipt["path"]
    if not isinstance(locator, str) or not locator or "\\" in locator:
        raise ValueError("Sales Plan original source locator must be canonical")
    relative = PurePosixPath(locator)
    if (
        relative.is_absolute()
        or relative.as_posix() != locator
        or ".." in relative.parts
    ):
        raise ValueError("Sales Plan original source locator must be canonical")
    if source_receipt["sha256"] != file_hash(paths[1]):
        raise ValueError("Actuals differ from the source confirmed in the case")
    return paths[0], paths[1], case


def page_offset(args: dict) -> int:
    """Accept only a nonnegative page index."""
    offset = args.get("offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("Invalid Sales Plan page offset")
    return offset


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    """Read the exact sealed revision, excluding full Actual and scenario tables."""
    current = context(binding, loaded, root, api)
    versions = current["saved"]["generations"]
    source_ref = args.get("source_ref")
    if source_ref is None and len(versions) == 1:
        source_ref = versions[0]["generation"]
    record = next((row for row in versions if row["generation"] == source_ref), None)
    if record is None:
        raise ValueError("Choose an exact persisted Sales Plan revision")
    if record.get("origin") == "native_draft":
        from native_sales_plan_authoring import registered_actual

        actual = registered_actual(record["actual_input_id"], loaded)
        if file_hash(actual) != file_hash(
            current["output"] / source_ref / "actuals.csv"
        ):
            raise ValueError(
                "Native Plan Actual copy differs from its registered source"
            )
        if record.get("seed_case_input_id"):
            selected_inputs(
                {
                    "case_input_id": record["seed_case_input_id"],
                    "actual_input_id": record["actual_input_id"],
                },
                loaded,
                api,
            )
    else:
        selected_inputs(record, loaded, api)
    directory = current["output"] / source_ref / "plan"
    refusal = current["output"] / source_ref / "native_contract_refusal.json"
    receipt = (
        {"status": "invalid_case"}
        if refusal.exists()
        else api.read_json(directory / "plan_execution_receipt.json")
    )
    rows = []
    if refusal.exists():
        rows.append(
            {
                "id": "native_contract_refusal.json",
                "title": "Scelte da correggere",
                "group": "native_contract_refusal.json",
                "data": api.read_json(refusal),
            }
        )
    for filename, title in (
        ("scenario_summary.csv", "Actual e Plan"),
        ("assumption_application_ledger.csv", "Applicazione delle ipotesi"),
    ):
        path = directory / filename
        if path.exists():
            with path.open(encoding="utf-8", newline="") as stream:
                for index, value in enumerate(csv.DictReader(stream)):
                    rows.append(
                        {
                            "id": filename + ":" + str(index),
                            "title": title + " · " + str(index + 1),
                            "group": filename,
                            "data": value,
                        }
                    )
    for filename, title in (
        ("reconciliation.json", "Esito e scarti"),
        ("prepared_evidence_manifest.json", "Tracciabilità"),
    ):
        if (directory / filename).exists():
            rows.append(
                {
                    "id": filename,
                    "title": title,
                    "group": filename,
                    "data": api.read_json(directory / filename),
                }
            )
    offset = page_offset(args)
    selection = next((row for row in rows if row["id"] == args.get("item_id")), None)
    if tree_hash(current["output"] / source_ref) != record["artifacts"]:
        raise ValueError("Sales Plan changed during reading")
    return {
        "revision": api.digest([loaded["run"], loaded["input_manifest"], record]),
        "items": [
            {key: row[key] for key in ("id", "title", "group")}
            for row in rows[offset : offset + 30]
        ],
        "total": len(rows),
        "selection": selection,
        "data": {
            "local_review_read_only": True,
            "status": receipt["status"],
            "report_ready": False,
            "professional_approval": False,
            "selection": {"source_ref": source_ref},
            "artifacts": list(record["artifacts"]),
            "verification": "Calcolo completo sulle righe osservate. Il riesame professionale del Plan e delle ipotesi resta necessario. Questa vista consulta riepilogo, ipotesi applicate, riconciliazione e provenienza. Per le righe dello scenario, apri una consultazione e dichiara domanda, filtri esatti e colonne.",
        },
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Persist one confirmed-case calculation, with exact-scope retry and recovery."""
    current = context(binding, loaded, root, api)
    if tool.startswith("vera_workspace_sales_plan_query"):
        from native_sales_plan_queries import dispatch as query_dispatch

        return query_dispatch(tool, args, binding, loaded, root, api, current)
    if tool in {
        "vera_workspace_sales_plan_draft_read",
        "vera_workspace_sales_plan_draft_save",
        "vera_workspace_sales_plan_draft_clear",
        "vera_workspace_sales_plan_source",
        "vera_workspace_sales_plan_members",
        "vera_workspace_sales_plan_calculate_draft",
    }:
        from native_sales_plan_authoring import dispatch as authoring_dispatch

        return authoring_dispatch(tool, args, binding, loaded, root, api, current)
    offset = page_offset(args)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_sales_plan_setup":
        inputs = [
            {
                "id": row["binding_id"],
                "title": Path(row["execution_relative_path"]).name,
                "kind": Path(row["execution_relative_path"]).suffix.lower(),
            }
            for row in loaded["input_manifest"]["inputs"]
            if Path(row["execution_relative_path"]).suffix.lower() in {".json", ".csv"}
        ]
        return {
            "work_ref": binding["work_ref"],
            "workflow": "sales-plan",
            "label": loaded["run"]["label"],
            "revision": current["revision"],
            "status": "recovery_required" if current["recovery_required"] else "ready",
            "can_write": writable and not current["recovery_required"],
            "items": inputs[offset : offset + 30],
            "offset": offset,
            "total": len(inputs),
            "has_more": offset + 30
            < max(len(inputs), len(current["saved"]["generations"])),
            "generations": [
                {"source_ref": row["generation"], "status": row["status"]}
                for row in current["saved"]["generations"][offset : offset + 30]
            ],
            "generations_total": len(current["saved"]["generations"]),
        }
    if tool == "vera_workspace_sales_plan_inspect":
        if args["revision"] != current["revision"]:
            raise ValueError("Stale Sales Plan selection")
        _, _, case = selected_inputs(args, loaded, api)
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "status": "inspection",
            "case": {
                key: case[key]
                for key in (
                    "purpose",
                    "preparation_recipe",
                    "reviewed_assumptions",
                    "professional_boundary",
                )
            },
        }
    if tool != "vera_workspace_sales_plan_calculate":
        raise ValueError("Unknown Sales Plan action")
    if not writable:
        raise PermissionError(
            "A running Sales Plan run and reviewer authority are required"
        )
    if args.get("human_reviewed") is not True:
        raise ValueError("Confirm the exact selected assumptions before calculation")
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid Sales Plan request key")
    actor, tenant = (
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
    )
    fingerprint = api.digest([tool, actor, tenant, binding, args])
    with api.write_lock(current["output"]):
        request_path = api.ui_state_directory(current["output"]) / (
            "sales-plan-request-" + api.digest([actor, tenant, key]) + ".json"
        )
        if request_path.exists():
            request = api.read_json(request_path)
            if request["request_sha256"] != fingerprint:
                raise ValueError("Sales Plan key belongs to a different request")
            if "result" not in request:
                raise ValueError("Interrupted Sales Plan requires specialist recovery")
            return request["result"]
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if current["recovery_required"]:
            raise ValueError("Existing Sales Plan outputs require specialist recovery")
        if args["revision"] != current["revision"]:
            raise ValueError("Stale Sales Plan setup; reload before calculating")
        case_path, actual_path, case = selected_inputs(args, loaded, api)
        generation = "sales-plan-" + api.digest(
            [
                args["case_input_id"],
                args["actual_input_id"],
                file_hash(case_path),
                file_hash(actual_path),
                current["implementation"],
            ]
        )
        record = next(
            (
                r
                for r in current["saved"]["generations"]
                if r["generation"] == generation
            ),
            None,
        )
        api.atomic_json(request_path, {"request_sha256": fingerprint})
        if record is None:
            destination = current["output"] / generation
            destination.mkdir()
            # Preserve the exact original case and Actuals, then derive only the source locator.
            (destination / "original-case.json").write_bytes(case_path.read_bytes())
            (destination / "actuals.csv").write_bytes(actual_path.read_bytes())
            case["files"]["actual_sales"]["path"] = "actuals.csv"
            api.atomic_json(destination / "case.json", case)
            engine_call(
                root,
                {
                    "operation": "run",
                    "case": str(destination / "case.json"),
                    "context": str(loaded["context_path"]),
                    "output": str(destination / "plan"),
                },
            )
            api.load_binding(binding)
            if (
                engine_call(root, {"operation": "implementation"})
                != current["implementation"]
                or file_hash(destination / "actuals.csv") != file_hash(actual_path)
                or file_hash(destination / "original-case.json") != file_hash(case_path)
            ):
                raise ValueError(
                    "Sales Plan sources or implementation changed during calculation"
                )
            produced = api.read_json(destination / "plan/plan_execution_receipt.json")
            if (
                produced["report_ready"] is not False
                or produced["case_sha256"] != file_hash(destination / "case.json")
                or produced["source_sha256"] != file_hash(actual_path)
            ):
                raise ValueError(
                    "Sales Plan receipt differs from the selected contract"
                )
            record = {
                "generation": generation,
                "case_input_id": args["case_input_id"],
                "actual_input_id": args["actual_input_id"],
                "implementation": current["implementation"],
                "status": produced["status"],
                "artifacts": tree_hash(destination),
            }
            current["saved"]["generations"].append(record)
            api.atomic_json(
                current["private"] / "sales-plan-state.json", current["saved"]
            )
        result = {
            "saved": True,
            "status": record["status"],
            "source_ref": generation,
            "professional_approval": False,
            "report_ready": False,
            "run_completed": False,
        }
        api.atomic_json(request_path, {"request_sha256": fingerprint, "result": result})
        return result
