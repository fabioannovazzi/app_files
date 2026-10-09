"""Attributed exact-record decisions become fresh public ledger cases and runs.

Identity, receipt integrity, CAS and public dependency gates are mechanical
audit requirements. No code judges a valuation or supplies human acceptance.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from native_archive_navigation import archive_module, engagement_scope, work_ref
from native_bank_preparation import file_hash

__all__ = ["audit_review", "dispatch", "record_rows"]

COLLECTIONS = {
    "mandate_assessment",
    "methods",
    "normalization_adjustments",
    "statements",
    "claims",
    "conclusion",
}
FIELDS = {"decision", "reviewer", "reviewed_at", "basis"}


def audit_review(output: Path, api: Any) -> dict:
    """An interrupted successor is never adopted or silently repeated."""
    private = api.ui_state_directory(output, create=False)
    requests = list(private.glob("valuation-review-request-*.json"))
    records = [api.read_json(p) for p in requests]
    expected = {
        p.name.replace("valuation-review-request-", "valuation-reviewed-case-")
        for p in requests
    }
    orphaned = any(
        p.name not in expected for p in private.glob("valuation-reviewed-case-*.json")
    )
    for path, record in zip(requests, records):
        if "result" in record and Path(
            record["case_path"]
        ) != private / path.name.replace(
            "valuation-review-request-", "valuation-reviewed-case-"
        ):
            raise ValueError("Reviewed valuation receipt selects another case path")
    for record in records:
        if (
            "result" in record
            and file_hash(Path(record["case_path"])) != record["case_sha256"]
        ):
            raise ValueError("Valuation reviewed case changed")
    return {
        "recovery_required": orphaned or any("result" not in r for r in records),
        "requests": records,
    }


def fields(value: Any, *, final: bool) -> dict:
    """Retain literal attribution; names are not authenticated professional identity."""
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Use complete literal valuation review fields")
    if any(not isinstance(v, str) or len(v) > 4000 for v in value.values()):
        raise ValueError("Invalid valuation review text")
    if value["decision"] not in {"", "accepted", "rejected", "changes_requested"}:
        raise ValueError("Choose an explicit professional decision")
    if final:
        if any(not v.strip() for v in value.values()):
            raise ValueError("Supply actual decision, reviewer, review time and basis")
        timestamp = datetime.fromisoformat(value["reviewed_at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Review time must include its actual timezone")
    return value


def record_rows(report: dict, collection: str) -> list:
    """Enumerate complete public rows; group identity adds mechanical provenance only."""
    if collection == "normalization_adjustments":
        return [
            {**row, "normalization_id": group["id"]}
            for group in report["normalizations"]
            for row in group.get("adjustments", [])
        ]
    value = report[collection]
    return value if isinstance(value, list) else [] if value is None else [value]


def declared_review(report: dict, collection: str, record: dict) -> dict | None:
    """Show literal case attribution separately from public eligibility/status."""
    case = report["case"]
    if collection == "mandate_assessment":
        target = case.get("mandate_details")
    elif collection == "conclusion":
        target = case.get("conclusion")
    elif collection == "normalization_adjustments":
        group = next(
            row
            for row in case["normalizations"]
            if row["id"] == record["normalization_id"]
        )
        target = next(row for row in group["adjustments"] if row["id"] == record["id"])
    else:
        identity = "method_id" if collection == "methods" else "id"
        target = next(row for row in case[collection] if row["id"] == record[identity])
    return target.get("review") if target else None


def acceptance_available(report: dict, collection: str, record: dict) -> bool:
    """Reflect exact public readiness; the producer independently gates the commit."""
    if not record.get("dependency_sha256"):
        return False
    if collection == "conclusion":
        methods = {row["method_id"]: row for row in report["methods"]}
        claims = {row["id"]: row for row in report["claims"]}
        return (
            report["mandate_assessment"]["status"] == "accepted_workpaper"
            and all(
                methods[key]["status"] == "accepted_workpaper"
                for key in record["method_ids"]
            )
            and all(
                claims[key]["status"] == "accepted_workpaper"
                for key in record.get("claim_ids", [])
            )
        )
    return record["status"] in {
        "ready_for_professional_review",
        "accepted_workpaper",
    } and record.get("review_dependencies_ready", True)


def selection(args: dict, report: dict) -> tuple[str, dict]:
    collection, index = args["collection"], args["index"]
    if collection not in COLLECTIONS:
        raise ValueError("Choose a professionally reviewable valuation record")
    rows = record_rows(report, collection)
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < len(rows)
    ):
        raise ValueError("Choose an exact current valuation record")
    row = rows[index]
    if not isinstance(row, dict):
        raise ValueError("Invalid public valuation record")
    if row.get("dependency_sha256") is not None and not re.fullmatch(
        r"[0-9a-f]{64}", row["dependency_sha256"]
    ):
        raise ValueError("Invalid public dependency digest")
    return f"{collection}:{index}", row


def draft(current: dict, identity: str, args: dict, api: Any) -> tuple[Path, dict, str]:
    path = current["private"] / (
        "valuation-review-draft-" + api.digest([args["source_ref"], identity]) + ".json"
    )
    scope = [current["scope"], args["source_ref"], identity]
    saved = api.read_json(path) if path.exists() else None
    if saved and saved["scope"] != scope:
        raise ValueError("Valuation review draft belongs to a changed scope")
    value = saved or {
        "scope": scope,
        "generation": 0,
        "fields": dict.fromkeys(FIELDS, ""),
    }
    fields(value["fields"], final=False)
    return path, value, api.digest(value)


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Preserve predecessor bytes; explicit decisions prepare a separate successor."""
    from native_valuation import bounded, context, engine_call, replay

    current = context(binding, loaded, root, api)
    row, report = replay(current, args["source_ref"], loaded, root, api)
    identity, record = selection(args, report)
    path, saved, stamp = draft(current, identity, args, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_valuation_review_read":
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "source_ref": args["source_ref"],
                "collection": args["collection"],
                "index": args["index"],
                "selection": {"id": identity},
                "data": {"selection": {"source_ref": args["source_ref"]}},
                "record": record,
                "declared_review": declared_review(report, args["collection"], record),
                "draft": saved["fields"],
                "draft_revision": stamp,
                "can_write": writable,
                "can_accept": acceptance_available(report, args["collection"], record),
                "professional_approval": False,
            }
        )
    if tool not in {
        "vera_workspace_valuation_review_draft_save",
        "vera_workspace_valuation_review_commit",
    }:
        raise ValueError("Unknown valuation review action")
    if not writable:
        raise PermissionError(
            "Review requires an owned running run and reviewer authority"
        )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if loaded["run"]["status"] != "running" or args["item_id"] != identity:
            raise PermissionError("Review the exact displayed running valuation record")
        # A completed commit may replay its immutable successor even after the
        # predecessor revision changed because its journal now contains the result.
        key = args.get("idempotency_key")
        intent = None
        request_sha = api.digest([current["scope"], tool, args])
        if tool.endswith("_commit"):
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid valuation review request key")
            intent = current["private"] / (
                "valuation-review-request-"
                + api.digest([current["scope"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                prior = api.read_json(intent)
                if prior["request_sha256"] != request_sha or "result" not in prior:
                    raise ValueError(
                        "Changed review retry or uncertain successor requires recovery"
                    )
                successor = api.load_binding(prior["binding"])
                if file_hash(Path(prior["case_path"])) != prior["case_sha256"]:
                    raise ValueError("Reviewed successor changed")
                if successor["run"]["run_id"] != prior["result"]["run_id"]:
                    raise ValueError("Review receipt selected another successor")
                return prior["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen the current valuation record")
        row, report = replay(current, args["source_ref"], loaded, root, api)
        selection(args, report)
        path, saved, stamp = draft(current, identity, args, api)
        if args["expected_draft_revision"] != stamp:
            raise ValueError("Valuation review draft changed concurrently")
        if tool.endswith("_draft_save"):
            updated = {
                **saved,
                "generation": saved["generation"] + 1,
                "fields": fields(args["fields"], final=False),
            }
            api.atomic_json(path, updated)
            return {
                "saved": True,
                "draft_revision": api.digest(updated),
                "professional_approval": False,
            }
        if args.get("confirmed") is not True:
            raise PermissionError("Confirm the actual selected professional decision")
        review = fields(saved["fields"], final=True)
        core = archive_module(api.archive_root)
        folder, _ = engagement_scope(
            core, binding["client_id"], binding["engagement_id"]
        )
        if folder.resolve() != Path(binding["client_root"]).resolve():
            raise PermissionError("The successor belongs to another archive client")
        original_case = next(
            r
            for r in loaded["input_manifest"]["inputs"]
            if r["binding_id"] == row["case_input_id"]
        )
        checked = engine_call(
            root,
            {
                "operation": "review",
                "case": str(
                    Path(loaded["run_root"]) / original_case["execution_relative_path"]
                ),
                "context": str(loaded["context_path"]),
                "collection": args["collection"],
                "index": args["index"],
                "review": review,
            },
        )
        case_path = current["private"] / (
            "valuation-reviewed-case-"
            + api.digest([current["scope"]["owner"], key])
            + ".json"
        )
        api.atomic_json(intent, {"request_sha256": request_sha})
        api.atomic_json(case_path, checked["case"])
        imported = core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            case_path.resolve(),
            "source",
        )["receipt"]
        inputs = loaded["input_manifest"]["inputs"]
        prepared = core.prepare_studio_client_workflow(
            binding["engagement_id"],
            "business-valuation",
            input_ids=list(
                dict.fromkeys(
                    [
                        *[
                            r["binding_id"]
                            for r in inputs
                            if r["kind"] != "upstream_artifact"
                        ],
                        imported["input_id"],
                    ]
                )
            ),
            upstream_artifacts=[
                {
                    "run_id": r["upstream_run_id"],
                    "artifact_id": r["upstream_artifact_id"],
                    "role": r["role"],
                }
                for r in inputs
                if r["kind"] == "upstream_artifact"
            ],
            label="Valutazione: decisione su " + identity,
            purpose="Conservare la decisione attribuita e riesaminare il caso successore.",
            idempotency_key="native-valuation-review-"
            + api.digest([current["scope"]["owner"], key]),
            new_run=True,
        )
        run_id = prepared["run"]["run_id"]
        core.start_studio_client_workflow(
            binding["client_id"], binding["engagement_id"], run_id
        )
        successor_binding = {**binding, "run_id": run_id}
        successor_binding["work_ref"] = work_ref(
            binding["client_id"], binding["engagement_id"], run_id
        )
        successor = api.load_binding(successor_binding)
        receipt = {
            "saved": True,
            "status": "reviewed_successor_case_registered",
            "work_ref": successor_binding["work_ref"],
            "run_id": run_id,
            "case_input_id": imported["input_id"],
            "record_status": checked["record"]["status"],
            "case_calculated": False,
            "run_completed": False,
            "piv_conformity": "not_assessed",
        }
        if (
            current["scope"]
            != context(binding, api.load_binding(binding), root, api)["scope"]
        ):
            raise ValueError(
                "Valuation predecessor changed during successor conservation"
            )
        successor_case = next(
            r
            for r in successor["input_manifest"]["inputs"]
            if r["binding_id"] == imported["input_id"]
        )
        if file_hash(
            Path(successor["run_root"]) / successor_case["execution_relative_path"]
        ) != file_hash(case_path):
            raise ValueError("Reviewed successor case differs from retained decision")
        api.atomic_json(
            intent,
            {
                "request_sha256": request_sha,
                "case_path": str(case_path),
                "case_sha256": file_hash(case_path),
                "binding": successor_binding,
                "result": receipt,
            },
        )
        return receipt
