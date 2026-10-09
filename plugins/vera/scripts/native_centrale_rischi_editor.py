"""Recoverable app-only pending CR recipes with exact grant and proposal CAS."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from native_centrale_rischi import (
    context,
    engine_call,
    grant_record,
    proposal_revision,
    read_source,
    retain_result,
    validate_proposal,
)

__all__ = ["dispatch"]


def validate_fields(
    current: dict, grant: dict, fields: dict, root: Path, api: Any
) -> None:
    """Permit incomplete choices but refuse foreign provenance and invented classes."""
    validate_proposal(current, grant, fields, root, api)
    template = api.read_json(
        current["output"] / grant["source_ref"] / "suggested_recipe.json"
    )
    for key in (
        "entity",
        "currency",
        "analysis_mode",
        "analysis_objective",
        "audience",
        "table_id",
        "control_tolerance",
    ):
        if not isinstance(fields[key], str) or len(fields[key]) > 4000:
            raise ValueError("Invalid CR draft text")
    columns = fields["columns"]
    if (
        not isinstance(columns, dict)
        or not set(columns) <= set(template["columns"])
        or any(
            not isinstance(value, str) or len(value) > 4000
            for value in columns.values()
        )
    ):
        raise ValueError("Invalid CR draft columns")
    inspection = api.read_json(
        current["output"] / grant["source_ref"] / "inspection.json"
    )
    table = next(
        (t for t in inspection["tables"] if t["table_id"] == fields["table_id"]), None
    )
    if fields["table_id"] and table is None:
        raise ValueError("Choose an exact inspected CR table")
    if any(
        value and (table is None or value not in table["columns"])
        for value in columns.values()
    ):
        raise ValueError("Choose exact inspected CR columns")
    contract = engine_call(root, {"operation": "recipe_contract"})
    mappings = fields["value_mappings"]
    if not isinstance(mappings, dict) or set(mappings) != set(contract):
        raise ValueError("Invalid CR value mappings")
    for key, classes in contract.items():
        values = mappings[key]
        if not isinstance(values, dict) or any(
            not isinstance(k, str)
            or len(k) > 4000
            or not isinstance(v, str)
            or v not in ["", *classes]
            for k, v in values.items()
        ):
            raise ValueError("Invalid CR mapping class")
    totals = fields["control_totals"]
    if (
        not isinstance(totals, dict)
        or not set(totals) <= {"granted", "operational_granted", "used"}
        or any(not isinstance(v, str) or len(v) > 4000 for v in totals.values())
    ):
        raise ValueError("Invalid CR control totals")


def snapshot(
    current: dict, grant: dict, api: Any
) -> tuple[Path, dict | None, str, str, bool]:
    """Retain stale bytes for explicit discard; generation tombstones prevent ABA."""
    path = current["private"] / (
        "cr-editor-" + api.digest([current["owner"], grant["grant_ref"]]) + ".json"
    )
    stored = api.read_json(path) if path.exists() else None
    if stored and (
        stored["owner"] != current["owner"]
        or stored["grant_sha256"] != api.digest(grant)
        or stored["implementation"] != current["implementation"]
        or stored["inputs"] != grant["inputs"]
    ):
        raise PermissionError("CR draft belongs to another scope")
    proposal_stamp = proposal_revision(current, grant, api)
    stale = bool(
        stored
        and stored["fields"] is not None
        and stored["base_proposal_revision"] != proposal_stamp
    )
    return path, stored, api.digest(stored) if stored else "", proposal_stamp, stale


def dispatch(
    action: str,
    args: dict,
    binding: dict,
    loaded: dict,
    root: Path,
    api: Any,
    current: dict,
) -> dict:
    """Keep app editing, pending proposal conservation and named calculation separate."""
    grant = grant_record(current, args, api)
    if grant["kind"] != "recipe":
        raise ValueError("CR recipe editor requires an exact inspection grant")
    if action not in {"recipe_read", "recipe_save", "recipe_clear", "recipe_stage"}:
        raise ValueError("Unknown CR recipe action")
    path, stored, stamp, proposal_stamp, stale = snapshot(current, grant, api)
    if action == "recipe_read":
        candidate_path = current["private"] / (grant["grant_ref"] + "-proposal.json")
        candidate = api.read_json(candidate_path) if candidate_path.exists() else None
        if candidate and (
            candidate["owner"] != current["owner"]
            or candidate["grant_sha256"] != api.digest(grant)
        ):
            raise PermissionError("CR proposal belongs to another grant")
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "selection": {"id": grant["grant_ref"]},
            "data": {"selection": {"source_ref": grant["source_ref"]}},
            "grant_ref": grant["grant_ref"],
            "question": grant["question"],
            "fields": (
                candidate["proposal"]
                if candidate
                else api.read_json(
                    current["output"] / grant["source_ref"] / "suggested_recipe.json"
                )
            ),
            "draft": stored["fields"] if stored else None,
            "view_selector": (
                stored.get("view_selector")
                if stored and stored["fields"] is not None
                else None
            ),
            "draft_revision": stamp,
            "proposal_revision": proposal_stamp,
            "stale": stale,
            "tables": api.read_json(
                current["output"] / grant["source_ref"] / "inspection.json"
            )["tables"],
            "classes": engine_call(root, {"operation": "recipe_contract"}),
            "column_fields": list(
                api.read_json(
                    current["output"] / grant["source_ref"] / "suggested_recipe.json"
                )["columns"]
            ),
            "can_write": not current["recovery_required"]
            and loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
            "professional_approval": False,
        }
    if loaded["run"]["status"] != "running" or "REVIEWER" not in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(","):
        raise PermissionError("CR draft writes require an owned running reviewer run")
    with api.write_lock(current["output"]):
        current = context(binding, api.load_binding(binding), root, api)
        grant = grant_record(current, args, api)
        fingerprint = api.digest([action, current["owner"], args])
        receipt = None
        if action == "recipe_stage":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", args["idempotency_key"]):
                raise ValueError("Invalid CR request key")
            receipt = current["private"] / (
                "cr-request-"
                + api.digest([current["owner"], args["idempotency_key"]])
                + ".json"
            )
            if receipt.exists():
                saved = api.read_json(receipt)
                if saved["request_sha256"] != fingerprint or "result" not in saved:
                    raise ValueError("Different or interrupted CR recipe request")
                return saved["result"]
        if current["recovery_required"] or args["revision"] != current["revision"]:
            raise ValueError("Stale or uncertain CR scope")
        if (
            args["item_id"] != grant["grant_ref"]
            or args["source_ref"] != grant["source_ref"]
        ):
            raise ValueError("CR editor requires its exact selected grant")
        path, stored, stamp, proposal_stamp, stale = snapshot(current, grant, api)
        if (
            args["expected_draft_revision"] != stamp
            or args["expected_proposal_revision"] != proposal_stamp
        ):
            raise ValueError("Stale CR draft or proposal checkpoint")
        if stale and action != "recipe_clear":
            raise ValueError(
                "CR draft base proposal changed; retain or explicitly discard"
            )
        if action in {"recipe_save", "recipe_clear"}:
            fields = None if action == "recipe_clear" else args["fields"]
            view_selector = None if fields is None else args.get("view_selector")
            if fields is not None:
                validate_fields(current, grant, fields, root, api)
                if view_selector is not None:
                    if (
                        not isinstance(view_selector, dict)
                        or set(view_selector) != {"field", "offset"}
                        or view_selector["field"]
                        not in {
                            "original_duration",
                            "residual_duration",
                            "risk_category",
                        }
                    ):
                        raise ValueError("Invalid CR editor value-page selector")
                    column = fields["columns"].get(view_selector["field"], "")
                    if not column or not fields["table_id"]:
                        raise ValueError(
                            "CR editor value page requires its mapped source column"
                        )
                    read_source(
                        current,
                        api.load_binding(binding),
                        root,
                        {
                            "source_ref": grant["source_ref"],
                            "source_selector": {
                                "table_id": fields["table_id"],
                                "kind": "values",
                                "column": column,
                                "offset": view_selector["offset"],
                            },
                        },
                        api,
                    )
            record = {
                "owner": current["owner"],
                "grant_sha256": api.digest(grant),
                "implementation": current["implementation"],
                "inputs": grant["inputs"],
                "base_proposal_revision": proposal_stamp,
                "fields": fields,
                "view_selector": view_selector,
                "generation": stored["generation"] + 1 if stored else 1,
            }
            api.atomic_json(path, record)
            return {
                "saved": True,
                "draft_revision": api.digest(record),
                "professional_approval": False,
            }
        if not stored or stored["fields"] is None or args["confirmed"] is not True:
            raise ValueError(
                "Choose and explicitly confirm the complete saved CR draft"
            )
        fields = stored["fields"]
        validate_fields(current, grant, fields, root, api)
        assert receipt is not None
        api.atomic_json(receipt, {"request_sha256": fingerprint})
        api.atomic_json(
            current["private"]
            / (grant["grant_ref"] + "-proposal-" + api.digest(fields) + ".json"),
            fields,
        )
        api.atomic_json(
            current["private"] / (grant["grant_ref"] + "-proposal.json"),
            {
                "owner": current["owner"],
                "grant_sha256": api.digest(grant),
                "proposal": fields,
            },
        )
        # A tombstone follows proposal conservation; interruptions remain auditable.
        api.atomic_json(
            path,
            {
                **stored,
                "fields": None,
                "generation": stored["generation"] + 1,
                "base_proposal_revision": proposal_revision(current, grant, api),
            },
        )
        return retain_result(
            api,
            receipt,
            fingerprint,
            {
                "saved": True,
                "status": "proposal_pending_review",
                "proposal_sha256": api.digest(fields),
                "professional_approval": False,
            },
        )
