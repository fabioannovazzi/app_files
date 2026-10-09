"""Bounded native AML reads and recoverable human decisions over immutable records."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_assetti import enrich_selection, extra_rows, profile
from native_bank_preparation import file_hash

__all__ = ["dispatch", "read_prepared"]

DECISION_FIELDS = {
    "reviewer_ref",
    "reviewed_at",
    "conclusion",
    "next_review_date",
    "review_date_reason",
}


def bounded(value: dict) -> dict:
    """Refuse oversized private pages; keep the specialist record authoritative."""
    if len(json.dumps(value).encode()) > 2_000_000:
        raise ValueError(
            "AML page exceeds the native limit; use the specialist workflow"
        )
    return value


def engine_call(root: Path, request: dict) -> dict:
    """Isolate current producer imports; interrupted appends remain uncertain."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_aml_bridge.py")),
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
            completed.stderr.strip().splitlines()[-1] or "AML service refused"
        )
    return json.loads(completed.stdout)


def offset(args: dict) -> int:
    """Bound queue offsets mechanically, independently of case meaning."""
    value = args.get("offset", 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Invalid AML page offset")
    return value


def record_path(output: Path, ref: Any, prefix: str = "aml-review") -> Path:
    """Accept only an opaque producer record identity, never a browser path."""
    if not isinstance(ref, str) or not re.fullmatch(
        re.escape(prefix) + r"-[0-9a-f]{64}", ref
    ):
        raise ValueError("Choose an exact AML record")
    return output / (ref + ".json")


def read_record(
    root: Path, binding: dict, loaded: dict, ref: str, api: Any
) -> tuple[dict, dict]:
    """Check all immutable source receipts and reproduce the exact JSON/memo pair."""
    contract = profile(root)
    if binding["workflow_id"] != contract["workflow"]:
        raise PermissionError("AML record belongs to another workflow")
    output = Path(loaded["output_dir"])
    path = record_path(output, ref, contract["prefix"])
    record = api.read_json(path)
    hashes = {
        path.name: file_hash(path),
        path.with_suffix(".md").name: file_hash(path.with_suffix(".md")),
    }
    if (record["client_id"], record["engagement_id"], record["workflow_id"]) != (
        binding["client_id"],
        binding["engagement_id"],
        contract["workflow"],
    ):
        raise PermissionError("AML record belongs to another client or engagement")
    if ref != contract["prefix"] + "-" + record["record_sha256"]:
        raise ValueError("AML producer record identity changed")
    inputs = {
        Path(loaded["run_root"]) / row["execution_relative_path"]: row["sha256"]
        for row in loaded["input_manifest"]["inputs"]
    }
    for row in record["review"]["sources"]:
        relative = Path(row["path"])
        path_source = Path(loaded["run_root"]) / "inputs" / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path_source not in inputs
        ):
            raise PermissionError("AML source is outside registered run inputs")
        if (
            row["sha256"] != inputs[path_source]
            or file_hash(path_source) != row["sha256"]
        ):
            raise ValueError("AML source receipt changed")
    engine_call(
        root,
        {
            "operation": "replay",
            "record": str(path),
            "inputs": str(Path(loaded["run_root"]) / "inputs"),
            "client_id": binding["client_id"],
            "engagement_id": binding["engagement_id"],
        },
    )
    if {
        path.name: file_hash(path),
        path.with_suffix(".md").name: file_hash(path.with_suffix(".md")),
    } != hashes:
        raise ValueError("AML record changed during replay")
    return record, hashes


def catalogue(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    """Index exact producer names; no suspicion, relevance or latest-version inference."""
    output = Path(loaded["output_dir"])
    contract = profile(root)
    if binding["workflow_id"] != contract["workflow"]:
        raise PermissionError("AML belongs to another workflow")
    population = {}
    rows = []
    for path in sorted(output.glob(contract["prefix"] + "-*")):
        if path.suffix not in {".json", ".md"} or not re.fullmatch(
            re.escape(contract["prefix"]) + r"-[0-9a-f]{64}", path.stem
        ):
            raise ValueError("Unrecognized AML output requires specialist recovery")
        population[path.name] = file_hash(path)
        if path.suffix == ".json":
            row = api.read_json(path)
            if (row["client_id"], row["engagement_id"], row["workflow_id"]) != (
                binding["client_id"],
                binding["engagement_id"],
                contract["workflow"],
            ):
                raise PermissionError("AML catalogue contains a foreign client record")
            rows.append(
                {
                    "id": path.stem,
                    "title": row["review"]["as_of"] + " · " + row["status"],
                    "status": row["status"],
                    "as_of": row["review"]["as_of"],
                    "reviewed_at": row["review"]
                    .get("professional_decision", {})
                    .get("reviewed_at"),
                    "reviewer_ref": row["review"]
                    .get("professional_decision", {})
                    .get("reviewer_ref"),
                }
            )
    if any(
        name[:-3] + ".json" not in population
        for name in population
        if name.endswith(".md")
    ) or any(
        name[:-5] + ".md" not in population
        for name in population
        if name.endswith(".json")
    ):
        raise ValueError("Incomplete AML record/memo pair requires specialist recovery")
    implementation = engine_call(root, {"operation": "implementation"})
    authoring = {"recovery_required": False}
    if root.name in {"aml-review", "adeguati-assetti"}:
        from native_aml_authoring import audit_run

        authoring = audit_run(output, api, root.name)
    checkpoint = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            population,
            implementation,
            authoring,
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_aml_bridge.py")),
            file_hash(Path(__file__).with_name("native_assetti.py")),
        ]
    )
    return {
        "rows": rows,
        "checkpoint": checkpoint,
        "implementation": implementation,
        "authoring": authoring,
        "population": population,
    }


def _read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    """Expose only paginated labels and one selected producer section, with its limits."""
    contract = profile(root)
    current = catalogue(root, binding, loaded, api)
    ref = args.get("source_ref")
    if ref is None and len(current["rows"]) == 1:
        ref = current["rows"][0]["id"]
    if ref not in {row["id"] for row in current["rows"]}:
        raise ValueError("Choose an exact persisted AML record")
    record, hashes = read_record(root, binding, loaded, ref, api)
    review = record["review"]
    rows = [
        {
            "id": "assessment",
            "title": "Valutazione proposta",
            "group": "assessment",
            "data": {
                key: review[key]
                for key in (
                    "assessment",
                    "assessment_citations",
                    "scope",
                    "limitations",
                )
            },
        }
    ]
    rows += [
        {
            "id": "finding:" + api.digest(row["id"])[:32],
            "title": row["observation"],
            "group": "finding",
            "data": row,
        }
        for row in review["findings"]
    ]
    rows += [
        {"id": "basis:" + str(i), "title": row["title"], "group": "basis", "data": row}
        for i, row in enumerate(review["legal_basis"])
    ]
    if review["jurisdiction"] == "CH-GE":
        rows.append(
            {
                "id": "mandate",
                "title": "Perimetro del mandato CH-GE",
                "group": "mandate",
                "data": {key: review[key] for key in contract["jurisdiction_fields"]},
            }
        )
    if review.get("previous"):
        rows.append(
            {
                "id": "previous",
                "title": "Cambiamenti rispetto alla revisione precedente",
                "group": "previous",
                "data": {
                    key: review[key] for key in ("previous", "changes_since_previous")
                },
            }
        )
    if review.get("professional_decision"):
        decision = review["professional_decision"]
        rows.append(
            {
                "id": "decision",
                "title": "Decisione registrata",
                "group": "decision",
                "data": {
                    key: value
                    for key, value in decision.items()
                    if key != "finding_dispositions"
                },
            }
        )
        rows += [
            {
                "id": "disposition:" + api.digest(key)[:32],
                "title": "Esito del rilievo · " + key,
                "group": "disposition",
                "data": {"finding_id": key, "disposition": value},
            }
            for key, value in decision["finding_dispositions"].items()
        ]
    if record.get("calculation") is not None:
        rows.append(
            {
                "id": "calculation",
                "title": "Calcolo New Client disponibile",
                "group": "calculation",
                "data": record["calculation"],
            }
        )
    if contract["workflow"] == "adeguati-assetti":
        rows += extra_rows(review, api)
        rows[0]["data"].update(
            company_context=review["company_context"],
            proportionality_basis=review["proportionality_basis"],
        )
    start = offset(args)
    selection = next((row for row in rows if row["id"] == args.get("item_id")), None)
    if selection and selection["group"] in {"finding", "assessment"}:
        citations = selection["data"].get(
            "citations", selection["data"].get("assessment_citations", [])
        )
        ids = {row["source_id"] for row in citations}
        selection = {
            **selection,
            "sources": [row for row in review["sources"] if row["id"] in ids],
        }
    if selection and contract["workflow"] == "adeguati-assetti":
        selection = enrich_selection(selection, review)
    revision = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            ref,
            hashes,
            current["implementation"],
        ]
    )
    if args.get("revision") and args["revision"] != revision:
        raise ValueError("Stale AML record: reload the exact revision")
    return {
        "revision": revision,
        "items": [
            {key: row[key] for key in ("id", "title", "group")}
            for row in rows[start : start + 30]
        ],
        "selection": selection,
        "total": len(rows),
        "data": {
            "local_review_read_only": True,
            "intelligent_review_present": "intelligent_review" in review,
            "status": record["status"],
            "jurisdiction": review["jurisdiction"],
            "language": review.get("language", "it"),
            "as_of": review["as_of"],
            "scope": review["scope"],
            "limitations": review["limitations"],
            "proposal_sha256": record["proposal_sha256"],
            "assurance_limit": record["assurance_limit"],
            "decision_checkpoint": current["checkpoint"],
            "selection": {"source_ref": ref},
            "artifacts": list(hashes),
            "finding_count": len(review["findings"]),
            "can_decide": loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
            and not current["authoring"]["recovery_required"],
            "authoring_recovery_required": current["authoring"]["recovery_required"],
            "verification": contract["verification"],
        },
    }


def draft_path(output: Path, binding: dict, ref: str, api: Any) -> Path:
    """Keep recoverable human fields outside official outputs, in exact actor/run scope."""
    return api.ui_state_directory(output, create=False) / (
        ("assetti" if binding["workflow_id"] == "adeguati-assetti" else "aml")
        + "-draft-"
        + api.digest(
            [
                os.environ["VERA_WORKSPACE_ACTOR_ID"],
                os.environ["VERA_WORKSPACE_TENANT_ID"],
                binding,
                ref,
            ]
        )
        + ".json"
    )


def draft_read(path: Path, api: Any) -> tuple[dict, str]:
    """Read an integrity-checked private draft or an explicitly empty checkpoint."""
    if not path.exists():
        return {"fields": {}, "dispositions": {}}, ""
    value = api.read_json(path)
    unsigned = {key: item for key, item in value.items() if key != "draft_sha256"}
    if value["draft_sha256"] != api.digest(unsigned):
        raise ValueError("AML draft content changed")
    return value, value["draft_sha256"]


def _dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Persist bounded draft patches and append only a complete explicit professional decision."""
    contract = profile(root)
    prefix = contract["private_prefix"]
    if binding["workflow_id"] != contract["workflow"] or not tool.startswith(
        contract["tool_prefix"]
    ):
        raise PermissionError("Immutable record action belongs to another workflow")
    tool = tool.replace(contract["tool_prefix"], "vera_workspace_aml_", 1)
    if tool == "vera_workspace_aml_setup":
        current = catalogue(root, binding, loaded, api)
        start = offset(args)
        return bounded(
            {
                "work_ref": binding["work_ref"],
                "revision": current["checkpoint"],
                "label": loaded["run"]["label"],
                "items": current["rows"][start : start + 30],
                "total": len(current["rows"]),
                "offset": start,
                "has_more": start + 30 < len(current["rows"]),
            }
        )
    current = read_prepared(root, binding, loaded, args, api)
    ref = current["data"]["selection"]["source_ref"]
    record, _ = read_record(root, binding, loaded, ref, api)
    finding_ids = {row["id"] for row in record["review"]["findings"]}
    output = Path(loaded["output_dir"])
    path = draft_path(output, binding, ref, api)
    draft, stamp = draft_read(path, api)
    scope = [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        binding,
        ref,
        current["revision"],
    ]
    if stamp and draft["scope"] != scope:
        raise ValueError("AML draft belongs to a different source revision or owner")
    if tool == "vera_workspace_aml_draft_read":
        start = offset(args)
        ids = [row["id"] for row in record["review"]["findings"]][start : start + 30]
        return bounded(
            {
                "draft_revision": stamp,
                "fields": draft["fields"],
                "dispositions": {
                    key: draft["dispositions"].get(key, "") for key in ids
                },
                "finding_items": [
                    row for row in record["review"]["findings"] if row["id"] in ids
                ],
                "total": len(finding_ids),
                "offset": start,
                "has_more": start + 30 < len(finding_ids),
                "ready": finding_ids == set(draft["dispositions"])
                and all(value.strip() for value in draft["dispositions"].values())
                and DECISION_FIELDS <= draft["fields"].keys(),
                "interrupted": any(
                    "result" not in api.read_json(p)
                    for p in api.ui_state_directory(output, create=False).glob(
                        prefix + "-request-*.json"
                    )
                ),
            }
        )
    if tool not in {
        "vera_workspace_aml_draft_save",
        "vera_workspace_aml_draft_clear",
        "vera_workspace_aml_decide",
    }:
        raise ValueError("Unknown AML action")
    if not current["data"]["can_decide"]:
        raise PermissionError("A running AML run and reviewer authority are required")
    with api.write_lock(output):
        loaded = api.load_binding(binding)
        current = read_prepared(root, binding, loaded, args, api)
        draft, stamp = draft_read(path, api)
        if not current["data"]["can_decide"]:
            raise PermissionError("AML run authority changed before the write")
        if stamp and draft["scope"] != scope:
            raise ValueError(
                "AML draft belongs to a different source revision or owner"
            )
        if tool == "vera_workspace_aml_decide":
            if args.get("human_reviewed") is not True:
                raise ValueError(
                    "Confirm professional review of the exact complete proposal"
                )
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid AML request key")
            receipt = api.ui_state_directory(output) / (
                prefix + "-request-" + api.digest([scope[:2], key]) + ".json"
            )
            fingerprint = api.digest([tool, binding, scope[:2], args])
            if receipt.exists():
                saved = api.read_json(receipt)
                if saved["request_sha256"] != fingerprint:
                    raise ValueError("AML request key belongs to a different decision")
                if "result" not in saved:
                    raise ValueError(
                        "Interrupted AML append requires specialist recovery"
                    )
                replayed, _ = read_record(
                    root, binding, loaded, saved["result"]["source_ref"], api
                )
                if (
                    replayed["proposal_sha256"] != record["proposal_sha256"]
                    or replayed["status"] != saved["result"]["status"]
                ):
                    raise ValueError("AML retry outcome no longer matches its proposal")
                return saved["result"]
        if args["expected_draft_revision"] != stamp:
            raise ValueError("Concurrent AML draft change: reload before saving")
        if args["expected_checkpoint"] != current["data"]["decision_checkpoint"]:
            raise ValueError(
                "AML record population changed: review versions before continuing"
            )
        if tool == "vera_workspace_aml_draft_clear":
            path.unlink(missing_ok=True)
            return {"draft_revision": "", "discarded": True}
        if tool == "vera_workspace_aml_draft_save":
            fields, dispositions = args["fields"], args["dispositions"]
            if (
                not isinstance(fields, dict)
                or not fields.keys() <= DECISION_FIELDS
                or not isinstance(dispositions, dict)
                or len(dispositions) > 30
                or not dispositions.keys() <= finding_ids
            ):
                raise ValueError("AML draft fields are outside the exact proposal")
            if any(
                not isinstance(value, str) or len(value) > 4000
                for value in [*fields.values(), *dispositions.values()]
            ):
                raise ValueError("Invalid or oversized AML draft value")
            saved = {
                "scope": scope,
                "fields": {**draft["fields"], **fields},
                "dispositions": {**draft["dispositions"], **dispositions},
            }
            if len(json.dumps(saved).encode()) > 4_000_000:
                raise ValueError("AML draft exceeds its bounded record contract")
            saved["draft_sha256"] = api.digest(saved)
            api.ui_state_directory(output)
            api.atomic_json(path, saved)
            return {"draft_revision": saved["draft_sha256"], "draft_saved": True}
        if any(
            "result" not in api.read_json(p)
            for p in api.ui_state_directory(output, create=False).glob(
                prefix + "-request-*.json"
            )
        ):
            raise ValueError(
                "Interrupted AML append requires specialist recovery; do not repeat"
            )
        if (
            not DECISION_FIELDS <= draft["fields"].keys()
            or set(draft["dispositions"]) != finding_ids
            or any(not value.strip() for value in draft["dispositions"].values())
        ):
            raise ValueError(
                "Address every finding and complete the professional decision"
            )
        decision = {
            "proposal_sha256": record["proposal_sha256"],
            **draft["fields"],
            "finding_dispositions": draft["dispositions"],
        }
        if not decision["next_review_date"]:
            decision["next_review_date"] = None
        # Validate without writes before persisting an uncertain append intent.
        staged = api.ui_state_directory(output) / (
            prefix + "-decision-" + api.digest(decision) + ".json"
        )
        api.atomic_json(staged, decision)
        engine_request = {
            "operation": "validate_decision",
            "record": str(record_path(output, ref, contract["prefix"])),
            "inputs": str(Path(loaded["run_root"]) / "inputs"),
            "client_id": binding["client_id"],
            "engagement_id": binding["engagement_id"],
            "decision": str(staged),
            "output": str(output),
        }
        engine_call(root, engine_request)
        before = catalogue(root, binding, api.load_binding(binding), api)
        if before["checkpoint"] != current["data"]["decision_checkpoint"]:
            raise ValueError(
                "AML source, implementation or outputs changed during decision validation"
            )
        api.atomic_json(receipt, {"request_sha256": fingerprint})
        response = engine_call(root, {**engine_request, "operation": "decide"})
        loaded = api.load_binding(binding)
        produced, produced_hashes = read_record(
            root, binding, loaded, response["record_ref"], api
        )
        after = catalogue(root, binding, loaded, api)
        if after["implementation"] != before["implementation"] or after[
            "population"
        ] != {**before["population"], **produced_hashes}:
            raise ValueError(
                "AML implementation or other records changed during append; specialist recovery required"
            )
        if (
            produced["proposal_sha256"] != record["proposal_sha256"]
            or produced["review"]["professional_decision"] != decision
        ):
            raise ValueError("AML saved decision differs from the reviewed proposal")
        result = {
            "saved": True,
            "status": produced["status"],
            "source_ref": response["record_ref"],
            "authenticated_signature": False,
            "run_completed": False,
        }
        api.atomic_json(receipt, {"request_sha256": fingerprint, "result": result})
        path.unlink(missing_ok=True)
        return result


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    """Read exact records with errors attributed to their maintained workflow."""
    try:
        return _read_prepared(root, binding, loaded, args, api)
    except (ValueError, PermissionError) as error:
        if root.name == "adeguati-assetti":
            raise type(error)(str(error).replace("AML", "Adeguati assetti")) from error
        raise


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Keep the two explicit producer routes and their professional boundaries distinct."""
    if tool.startswith(
        ("vera_workspace_aml_author_", "vera_workspace_assetti_author_")
    ):
        from native_aml_authoring import dispatch as author_dispatch

        try:
            return author_dispatch(tool, args, binding, loaded, root, api)
        except (ValueError, PermissionError) as error:
            if root.name == "adeguati-assetti":
                raise type(error)(
                    str(error).replace("AML", "Adeguati assetti")
                ) from error
            raise
    try:
        return _dispatch(tool, args, binding, loaded, root, api)
    except (ValueError, PermissionError) as error:
        if root.name == "adeguati-assetti":
            raise type(error)(str(error).replace("AML", "Adeguati assetti")) from error
        raise
