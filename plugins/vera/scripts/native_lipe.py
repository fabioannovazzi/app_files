"""Native selection and immutable calculation reads over the maintained LIPE CLI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "read_prepared"]


def engine_call(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Keep engine imports isolated and retain uncertainty after interrupted writes."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_lipe_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1] or "LIPE calculation refused"
        )
    return json.loads(completed.stdout)


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Verify the exact native receipt population before showing or executing work."""
    if binding["workflow_id"] != "lipe":
        raise PermissionError("LIPE belongs to another workflow")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    state_path = private / "lipe-state.json"
    saved = api.read_json(state_path) if state_path.exists() else {"generations": []}
    implementation = engine_call(root, {"operation": "implementation"})
    known = set()
    for row in saved["generations"]:
        if (
            not re.fullmatch(r"lipe-[0-9a-f]{64}", row["generation"])
            or row["generation"] in known
        ):
            raise ValueError("Invalid LIPE generation identity")
        known.add(row["generation"])
        if row["implementation"] != implementation:
            raise ValueError("LIPE revision belongs to a changed implementation")
        if tree_hash(output / row["generation"]) != row["artifacts"]:
            raise ValueError("LIPE calculation artifacts or their population changed")
    unresolved = any(
        "result" not in api.read_json(path)
        for path in private.glob("lipe-request-*.json")
    )
    unknown = any(path.name not in known for path in output.glob("lipe-*"))
    return {
        "output": output,
        "private": private,
        "saved": saved,
        "implementation": implementation,
        "recovery_required": unresolved or unknown,
        "revision": api.digest(
            [
                loaded["run"],
                loaded["input_manifest"],
                saved,
                implementation,
                file_hash(Path(__file__)),
                file_hash(Path(__file__).with_name("native_lipe_bridge.py")),
            ]
        ),
    }


def input_case(identity: str, binding: dict, loaded: dict, api: Any) -> Path:
    """Bind all declared evidence to registered immutable inputs, including synthetic cases."""
    inputs = {row["binding_id"]: row for row in loaded["input_manifest"]["inputs"]}
    if identity not in inputs:
        raise ValueError("Case input is outside this LIPE run")
    # load_run hydrates the portable context; browser state never supplies a path.
    run_root = Path(loaded["run_root"])
    path = run_root / inputs[identity]["execution_relative_path"]
    if path.suffix.lower() != ".json":
        raise ValueError("Select a reviewed JSON case")
    case = api.read_json(path)
    if (case.get("client_id"), case.get("engagement_id")) != (
        binding["client_id"],
        binding["engagement_id"],
    ):
        raise PermissionError("LIPE case and archive identity differ")
    registered = {
        (run_root / row["execution_relative_path"]).resolve(): row["sha256"]
        for row in inputs.values()
    }
    source_root = run_root / "inputs"
    for row in case.get("sources", []):
        source = source_root / row["path"]
        if (
            any(parent.is_symlink() for parent in (source, *source.parents))
            or source.resolve() not in registered
        ):
            raise PermissionError("LIPE source is outside registered run inputs")
        if (
            file_hash(source) != row["sha256"]
            or row["sha256"] != registered[source.resolve()]
        ):
            raise ValueError("LIPE source receipt differs from registered bytes")
    return path


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    """Project bounded exact producer rows; do not select a newer revision implicitly."""
    current = context(binding, loaded, root, api)
    versions = current["saved"]["generations"]
    selected_version = args.get("source_ref")
    if selected_version is None and len(versions) == 1:
        selected_version = versions[0]["generation"]
    record = next(
        (row for row in versions if row["generation"] == selected_version), None
    )
    if record is None:
        raise ValueError("Choose an exact persisted LIPE revision")
    input_case(record["case_input_id"], binding, loaded, api)
    result = api.read_json(current["output"] / selected_version / "result.json")
    revision = api.digest([loaded["run"], loaded["input_manifest"], record])
    rows = []
    titles = {
        "blockers": "Impedimenti",
        "modules": "Modulo VP",
        "findings": "Scarti da esaminare",
        "composition": "Composizione",
        "reconciliation": "Riconciliazione",
        "observations": "Osservazioni",
        "catalog_review": "Revisione del catalogo",
    }
    for group in (
        "blockers",
        "modules",
        "findings",
        "composition",
        "reconciliation",
        "observations",
        "catalog_review",
    ):
        values = result.get(group, [])
        if not isinstance(values, list):
            raise ValueError("Unsupported producer LIPE result structure")
        for index, value in enumerate(values):
            rows.append(
                {
                    "id": group + ":" + str(index),
                    "title": titles[group] + " · " + str(index + 1),
                    "group": group,
                    "data": value,
                }
            )
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid LIPE page offset")
    selection = next((row for row in rows if row["id"] == args.get("item_id")), None)
    if tree_hash(current["output"] / selected_version) != record["artifacts"]:
        raise ValueError("LIPE artifacts changed during reading")
    return {
        "revision": revision,
        "items": [
            {key: row[key] for key in ("id", "title", "group")}
            for row in rows[offset : offset + 30]
        ],
        "total": len(rows),
        "selection": selection,
        "data": {
            "local_review_read_only": True,
            "status": result["status"],
            "data_origin": api.read_json(
                current["output"] / selected_version / "case.json"
            ).get("data_origin"),
            "qualification": result.get(
                "qualification", "PILOT_NOT_PROFESSIONALLY_ACCEPTED"
            ),
            "export_status": "NOT_AUTHORIZED",
            "selection": {"source_ref": selected_version},
            "artifacts": list(record["artifacts"]),
            "verification": "Calculation only; reviewed classifications, completeness, professional approval, model-data session report and XML export remain in the maintained LIPE workflow.",
        },
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Execute only a signed, explicitly selected case; retain retry and uncertainty receipts."""
    current = context(binding, loaded, root, api)
    items = [
        {
            "id": row["binding_id"],
            "title": Path(row["execution_relative_path"]).name,
            "role": row["role"],
        }
        for row in loaded["input_manifest"]["inputs"]
        if Path(row["execution_relative_path"]).suffix.lower() == ".json"
    ]
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid LIPE page offset")
    if tool == "vera_workspace_lipe_setup":
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "workflow": "lipe",
            "label": loaded["run"]["label"],
            "status": "recovery_required" if current["recovery_required"] else "ready",
            "can_write": not current["recovery_required"]
            and loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
            "items": items[offset : offset + 30],
            "total": len(items),
            "offset": offset,
            "has_more": offset + 30 < len(items),
            "generations": [
                {
                    "source_ref": row["generation"],
                    "status": row["status"],
                    "case_input_id": row["case_input_id"],
                }
                for row in current["saved"]["generations"][offset : offset + 30]
            ],
            "generations_total": len(current["saved"]["generations"]),
        }
    if tool != "vera_workspace_lipe_calculate":
        raise ValueError("Unknown LIPE action")
    if (
        "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        or loaded["run"]["status"] != "running"
    ):
        raise PermissionError("A running LIPE run and reviewer authority are required")
    if args.get("human_reviewed") is not True:
        raise ValueError("Confirm the reviewed case selection before calculating")
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid calculation request key")
    actor = os.environ["VERA_WORKSPACE_ACTOR_ID"]
    tenant = os.environ["VERA_WORKSPACE_TENANT_ID"]
    fingerprint = api.digest([tool, actor, tenant, binding, args])
    with api.write_lock(current["output"]):
        receipt = api.ui_state_directory(current["output"]) / (
            "lipe-request-" + api.digest([actor, tenant, key]) + ".json"
        )
        if receipt.exists():
            saved = api.read_json(receipt)
            if saved["request_sha256"] != fingerprint:
                raise ValueError("Calculation key belongs to a different request")
            if "result" not in saved:
                raise ValueError(
                    "Interrupted LIPE request requires specialist recovery; do not repeat execution"
                )
            return saved["result"]
        current = context(binding, api.load_binding(binding), root, api)
        if current["recovery_required"]:
            raise ValueError(
                "Existing LIPE outputs or interrupted requests require specialist recovery"
            )
        if args["revision"] != current["revision"]:
            raise ValueError("Stale LIPE setup: reload before calculating")
        case_path = input_case(args["case_input_id"], binding, loaded, api)
        previous = next(
            (
                row
                for row in current["saved"]["generations"]
                if row["case_input_id"] == args["case_input_id"]
            ),
            None,
        )
        request = {"request_sha256": fingerprint}
        api.atomic_json(receipt, request)
        if previous is None:
            response = engine_call(
                root,
                {
                    "operation": "calculate",
                    "case": str(case_path),
                    "context": str(loaded["context_path"]),
                    "source_root": str(Path(loaded["run_root"]) / "inputs"),
                    "output": str(current["output"]),
                },
            )
            # Recheck source receipts after the producer has finished, before closing its outputs.
            api.load_binding(binding)
            if (
                engine_call(root, {"operation": "implementation"})
                != current["implementation"]
            ):
                raise ValueError("LIPE implementation changed during calculation")
            generation = response["generation"]
            if not re.fullmatch(r"lipe-[0-9a-f]{64}", generation):
                raise ValueError("Invalid producer LIPE revision")
            produced = api.read_json(current["output"] / generation / "result.json")
            if generation != "lipe-" + produced["result_hash"] or api.read_json(
                current["output"] / generation / "case.json"
            ) != api.read_json(case_path):
                raise ValueError("LIPE calculation does not match its selected case")
            previous = {
                "generation": generation,
                "case_input_id": args["case_input_id"],
                "implementation": current["implementation"],
                "artifacts": tree_hash(current["output"] / generation),
                "status": produced["status"],
            }
            current["saved"]["generations"].append(previous)
            api.atomic_json(current["private"] / "lipe-state.json", current["saved"])
        result = {
            "saved": True,
            "status": previous["status"],
            "source_ref": previous["generation"],
            "professional_approval": False,
            "run_completed": False,
        }
        api.atomic_json(receipt, {**request, "result": result})
        return result
