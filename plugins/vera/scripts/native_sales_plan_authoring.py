"""Recoverable professional Sales Plan choices over exact registered Actuals."""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "registered_actual"]

FIELDS = frozenset(
    {
        "actual_input_id",
        "seed_case_input_id",
        "purpose",
        "reporting_currency",
        "unit",
        "dimension_columns",
        "metric_columns",
        "period_mapping",
        "default_discount_behavior",
        "default_cogs_behavior",
        "same_driver_overlap_behavior",
        "discount_assumption_basis",
        "cogs_assumption_basis",
        "assumptions",
        "reviewed_by",
        "reviewed_at",
        "review_basis",
    }
)


def validate_fields(fields: object) -> dict:
    """Protect the editor's structural contract, without judging commercial meaning."""
    if (
        not isinstance(fields, dict)
        or not fields.keys() <= FIELDS
        or len(json.dumps(fields).encode()) > 96_000
    ):
        raise ValueError("Invalid or oversized Sales Plan authoring fields")
    text_fields = FIELDS - {
        "dimension_columns",
        "metric_columns",
        "period_mapping",
        "assumptions",
    }
    if any(
        not isinstance(fields[key], str) or len(fields[key]) > 8000
        for key in fields.keys() & text_fields
    ):
        raise ValueError("Invalid Sales Plan text field")

    def strings(value: object) -> bool:
        return isinstance(value, list) and all(
            isinstance(item, str) and len(item) <= 8000 for item in value
        )

    if "dimension_columns" in fields and not strings(fields["dimension_columns"]):
        raise ValueError("Invalid Sales Plan dimensions")
    if "metric_columns" in fields and (
        not isinstance(fields["metric_columns"], dict)
        or any(
            not isinstance(k, str) or not isinstance(v, str)
            for k, v in fields["metric_columns"].items()
        )
    ):
        raise ValueError("Invalid Sales Plan metric mapping")
    if "period_mapping" in fields:
        if not isinstance(fields["period_mapping"], list) or any(
            not isinstance(row, dict)
            or set(row) != {"source_period", "target_period"}
            or any(not isinstance(v, str) for v in row.values())
            for row in fields["period_mapping"]
        ):
            raise ValueError("Invalid Sales Plan period mapping")
    if "assumptions" in fields:
        if not isinstance(fields["assumptions"], list):
            raise ValueError("Invalid Sales Plan assumptions")
        for row in fields["assumptions"]:
            if (
                not isinstance(row, dict)
                or set(row)
                != {
                    "assumption_id",
                    "driver",
                    "change_pct",
                    "scope",
                    "effective_periods",
                    "priority",
                    "rationale",
                }
                or any(
                    not isinstance(row[k], str)
                    for k in ["assumption_id", "driver", "change_pct", "rationale"]
                )
                or type(row["priority"]) not in {str, int}
                or not strings(row["effective_periods"])
                or not isinstance(row["scope"], dict)
                or any(
                    not isinstance(k, str) or not strings(v)
                    for k, v in row["scope"].items()
                )
            ):
                raise ValueError("Invalid Sales Plan assumption structure")
    return fields


def owner_scope(binding: dict) -> list:
    """Portable run identities and OS actor namespaces are exact isolation controls."""
    return [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[
            binding[key]
            for key in ("client_id", "engagement_id", "run_id", "workflow_id")
        ],
    ]


def draft_path(current: dict, binding: dict, api: Any) -> Path:
    """Place unfinished choices outside the declared output tree."""
    return current["private"] / (
        "sales-plan-draft-" + api.digest(owner_scope(binding)) + ".json"
    )


def read_draft(current: dict, binding: dict, api: Any) -> dict:
    path = draft_path(current, binding, api)
    if not path.exists():
        return {"fields": {}, "draft_revision": "", "stale": False}
    value = api.read_json(path)
    content = {k: v for k, v in value.items() if k != "draft_revision"}
    if value["scope"] != owner_scope(binding) or value["draft_revision"] != api.digest(
        content
    ):
        raise ValueError("Sales Plan draft belongs to another actor or changed")
    return {
        "fields": validate_fields(value["fields"]),
        "draft_revision": value["draft_revision"],
        "stale": value["revision"] != current["revision"],
    }


def registered_actual(identity: str, loaded: dict) -> Path:
    """Resolve only the exact selected CSV receipt, without semantic file selection."""
    row = next(
        (r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity),
        None,
    )
    if row is None:
        raise PermissionError("Sales Plan Actual input is outside this run")
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if path.suffix.lower() != ".csv" or file_hash(path) != row["sha256"]:
        raise ValueError(
            "Sales Plan Actual input differs from its registered CSV receipt"
        )
    return path


def source_page(path: Path, args: dict) -> dict:
    """Page literal source rows or exact distinct members; never infer field meaning."""
    from native_sales_plan import page_offset

    offset = page_offset(args)
    before = file_hash(path)
    rows = []
    members = set()
    count = 0
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if (
            not headers
            or len(headers) > 35
            or len(set(headers)) != len(headers)
            or any(not h for h in headers)
        ):
            raise ValueError("Actual CSV requires distinct nonempty supported headers")
        column = args.get("column")
        if column is not None and column not in headers:
            raise ValueError("Unknown Actual member column")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError("Actual CSV rows differ from the header width")
            if column is None and offset <= count < offset + 20:
                rows.append(row)
            if column is not None:
                members.add(row[column])
            count += 1
    if file_hash(path) != before:
        raise ValueError("Actual source changed during inspection")
    if column is not None:
        # Exact membership and UI search are mechanical; all rows are scanned.
        values = sorted(v for v in members if args.get("query", "") in v)
        result = {
            "members": values[offset : offset + 30],
            "total": len(values),
            "has_more": offset + 30 < len(values),
            "column": column,
        }
    else:
        result = {
            "headers": headers,
            "rows": rows,
            "total": count,
            "has_more": offset + 20 < count,
        }
    result.update(offset=offset, source_sha256=before, population_rows_scanned=count)
    if len(json.dumps(result).encode()) > 100_000:
        raise ValueError(
            "Actual inspection page is oversized; use the specialist workflow"
        )
    return result


def compile_case(fields: dict, actual: Path, stamp: str, contract: dict) -> dict:
    """Encode explicitly chosen fields in the existing contract; the producer validates semantics."""
    required = FIELDS - {"seed_case_input_id"}
    if not required <= fields.keys():
        raise ValueError(
            "Complete all Sales Plan mapping, assumption and review choices"
        )
    for key in (
        "purpose",
        "reporting_currency",
        "unit",
        "reviewed_by",
        "reviewed_at",
        "review_basis",
    ):
        if not isinstance(fields[key], str) or not fields[key].strip():
            raise ValueError("Complete Sales Plan " + key)
    assumptions = json.loads(json.dumps(fields["assumptions"]))
    if not isinstance(assumptions, list) or not assumptions:
        raise ValueError("Provide at least one explicit Sales Plan assumption")
    for row in assumptions:
        priority = row["priority"]
        if isinstance(priority, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", priority):
            row["priority"] = int(priority)
    recipe_fields = (
        "reporting_currency",
        "unit",
        "dimension_columns",
        "metric_columns",
        "period_mapping",
        "default_discount_behavior",
        "default_cogs_behavior",
        "same_driver_overlap_behavior",
        "discount_assumption_basis",
        "cogs_assumption_basis",
    )
    return {
        "schema_version": contract["schema"],
        "case_id": "native-plan-" + stamp[:24],
        "purpose": fields["purpose"],
        "preparation_recipe": {
            **{k: fields[k] for k in recipe_fields},
            "recipe_id": contract["recipe"],
            "engine_version": contract["engine_version"],
            "arithmetic": "decimal_exact",
            "source_scenario": contract["source_scenario"],
            "target_scenario": contract["target_scenario"],
            "time_profile": contract["time_profile"],
            "fx_rate_definition": contract["fx_definition"],
        },
        "reviewed_assumptions": {
            "status": "reviewed",
            "reviewed_by": fields["reviewed_by"],
            "reviewed_at": fields["reviewed_at"],
            "review_basis": fields["review_basis"],
            "assumptions": assumptions,
        },
        "files": {"actual_sales": {"path": "actuals.csv", "sha256": file_hash(actual)}},
        "professional_boundary": {
            "prospective_assumptions_are_not_source_facts": True,
            "professional_approval_required": True,
            "report_ready": False,
        },
    }


def dispatch(
    tool: str,
    args: dict,
    binding: dict,
    loaded: dict,
    root: Path,
    api: Any,
    current: dict,
) -> dict:
    """Keep partial authoring, human confirmation, calculation and professional approval distinct."""
    from native_sales_plan import context, engine_call, selected_inputs

    if tool == "vera_workspace_sales_plan_draft_read":
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "draft": read_draft(current, binding, api),
            "contract": engine_call(root, {"operation": "contract"}),
        }
    if tool in {
        "vera_workspace_sales_plan_source",
        "vera_workspace_sales_plan_members",
    }:
        if args["revision"] != current["revision"]:
            raise ValueError("Stale Sales Plan source selection")
        result = source_page(registered_actual(args["actual_input_id"], loaded), args)
        return {
            **result,
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "status": "source_inspection",
        }
    if (
        "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        or loaded["run"]["status"] != "running"
    ):
        raise PermissionError(
            "A running Sales Plan run and reviewer authority are required"
        )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if current["recovery_required"]:
            raise ValueError("Existing Sales Plan outputs require specialist recovery")
        draft = read_draft(current, binding, api)
        if tool == "vera_workspace_sales_plan_calculate_draft":
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid Sales Plan calculation key")
            request_sha = api.digest([tool, owner_scope(binding), args])
            request_path = current["private"] / (
                "sales-plan-request-"
                + api.digest([owner_scope(binding), key])
                + ".json"
            )
            if request_path.exists():
                saved = api.read_json(request_path)
                if saved["request_sha256"] != request_sha:
                    raise ValueError("Sales Plan key belongs to another draft request")
                if "result" not in saved:
                    raise ValueError(
                        "Interrupted Sales Plan draft calculation requires recovery"
                    )
                return saved["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Stale Sales Plan authoring scope")
        if args["expected_draft_revision"] != draft["draft_revision"]:
            raise ValueError("Sales Plan draft changed concurrently")
        path = draft_path(current, binding, api)
        if tool == "vera_workspace_sales_plan_draft_clear":
            path.unlink(missing_ok=True)
            return {"discarded": True, "draft_revision": ""}
        if draft["stale"]:
            raise ValueError(
                "Sales Plan draft is stale; explicitly discard it before authoring"
            )
        if tool == "vera_workspace_sales_plan_draft_save":
            fields = validate_fields(args["fields"])
            if fields.get("actual_input_id"):
                registered_actual(fields["actual_input_id"], loaded)
            if fields.get("seed_case_input_id"):
                selected_inputs(
                    {
                        "case_input_id": fields["seed_case_input_id"],
                        "actual_input_id": fields["actual_input_id"],
                    },
                    loaded,
                    api,
                )
            value = {
                "scope": owner_scope(binding),
                "revision": current["revision"],
                "fields": fields,
            }
            value["draft_revision"] = api.digest(value)
            api.ui_state_directory(current["output"])
            api.atomic_json(path, value)
            return {"draft_saved": True, "draft_revision": value["draft_revision"]}
        if (
            tool != "vera_workspace_sales_plan_calculate_draft"
            or args.get("human_reviewed") is not True
        ):
            raise ValueError(
                "Confirm the exact saved Sales Plan draft before calculating"
            )
        actual = registered_actual(draft["fields"]["actual_input_id"], loaded)
        case = compile_case(
            draft["fields"],
            actual,
            draft["draft_revision"],
            engine_call(root, {"operation": "contract"}),
        )
        seed = None
        if draft["fields"].get("seed_case_input_id"):
            seed, _, _ = selected_inputs(
                {
                    "case_input_id": draft["fields"]["seed_case_input_id"],
                    "actual_input_id": draft["fields"]["actual_input_id"],
                },
                loaded,
                api,
            )
        generation = "sales-plan-" + api.digest(
            [draft["draft_revision"], current["implementation"]]
        )
        destination = current["output"] / generation
        api.atomic_json(request_path, {"request_sha256": request_sha})
        destination.mkdir()
        (destination / "actuals.csv").write_bytes(actual.read_bytes())
        if seed:
            (destination / "original-case.json").write_bytes(seed.read_bytes())
        api.atomic_json(destination / "case.json", case)
        api.atomic_json(
            destination / "native_case_review.json",
            {
                "schema_version": 1,
                "scope": owner_scope(binding),
                "draft_revision": draft["draft_revision"],
                "fields": draft["fields"],
                "actual_sha256": file_hash(actual),
                "professional_approval": False,
            },
        )
        execution = engine_call(
            root,
            {
                "operation": "run_draft",
                "case": str(destination / "case.json"),
                "context": str(loaded["context_path"]),
                "output": str(destination / "plan"),
            },
        )
        api.load_binding(binding)
        if (
            engine_call(root, {"operation": "implementation"})
            != current["implementation"]
            or file_hash(actual) != file_hash(destination / "actuals.csv")
            or api.read_json(destination / "case.json") != case
            or (
                seed is not None
                and file_hash(seed) != file_hash(destination / "original-case.json")
            )
        ):
            raise ValueError("Sales Plan draft source or implementation changed")
        if execution["exit_status"] == 2:
            if (destination / "plan/plan_execution_receipt.json").exists():
                raise ValueError("Contract refusal has an unexpected execution receipt")
            api.atomic_json(
                destination / "native_contract_refusal.json",
                {
                    "schema_version": 1,
                    "producer_contract_error": execution["contract_error"],
                    "report_ready": False,
                },
            )
            receipt = {"status": "invalid_case"}
        else:
            receipt = api.read_json(destination / "plan/plan_execution_receipt.json")
            if (
                receipt["source_sha256"] != file_hash(actual)
                or receipt["case_sha256"] != file_hash(destination / "case.json")
                or receipt["report_ready"] is not False
            ):
                raise ValueError("Sales Plan draft output receipt changed")
        record = {
            "generation": generation,
            "origin": "native_draft",
            "actual_input_id": draft["fields"]["actual_input_id"],
            "seed_case_input_id": draft["fields"].get("seed_case_input_id"),
            "draft_revision": draft["draft_revision"],
            "implementation": current["implementation"],
            "status": receipt["status"],
            "artifacts": tree_hash(destination),
        }
        current["saved"]["generations"].append(record)
        api.atomic_json(current["private"] / "sales-plan-state.json", current["saved"])
        result = {
            "saved": True,
            "status": receipt["status"],
            "source_ref": generation,
            "professional_approval": False,
            "report_ready": False,
            "run_completed": False,
        }
        api.atomic_json(request_path, {"request_sha256": request_sha, "result": result})
        return result
