"""Private CR source choices and literal questions; saving never grants model access."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from native_centrale_rischi import context, read_source, selected_inputs, version

__all__ = ["dispatch"]


def scope(current: dict, loaded: dict, root: Path, args: dict, api: Any) -> dict:
    """Fixed identities enforce isolation; humans choose sources and question meaning."""
    kind = args["kind"]
    reference = args.get("source_ref", "")
    selector = args.get("source_selector")
    page = None
    if kind == "intake":
        if reference or selector is not None:
            raise ValueError("CR source choices belong to the run intake")
    elif kind in {"question", "navigation"}:
        row = version(current, reference)
        if row["phase"] not in {"inspection", "analysis"}:
            raise ValueError("CR questions require an inspection or analysis")
        if kind == "navigation" and (
            row["phase"] != "inspection" or selector is not None
        ):
            raise ValueError("CR source navigation requires its exact inspection")
        if selector is not None:
            page = read_source(current, loaded, root, args, api)["source"]
            if page["page"]["kind"] == "tables" or not page["page"]["entries"]:
                raise ValueError(
                    "CR page questions require a nonempty exact source page"
                )
    else:
        raise ValueError("Unknown CR local draft kind")
    return {
        "kind": kind,
        "source_ref": reference,
        "source_selector": selector,
        "page": page,
    }


def defaults(kind: str) -> dict:
    """No source or substantive question is selected automatically."""
    if kind == "intake":
        return {"input_ids": [], "offset": 0}
    if kind == "navigation":
        return {
            "source_selector": {
                "table_id": "",
                "kind": "rows",
                "column": "",
                "offset": 0,
            }
        }
    return {"question": ""}


def snapshot(
    current: dict, exact: dict, loaded: dict, api: Any
) -> tuple[Path, dict | None, str]:
    """Full scope and generation hashes refuse lost updates and discarded-draft replay."""
    path = current["private"] / (
        "cr-local-draft-" + api.digest([current["owner"], exact]) + ".json"
    )
    stored = api.read_json(path) if path.exists() else None
    if stored and (
        stored["owner"] != current["owner"]
        or stored["scope"] != exact
        or stored["inputs"] != loaded["input_manifest"]
        or stored["implementation"] != current["implementation"]
    ):
        raise PermissionError("CR local draft belongs to another scope")
    return path, stored, api.digest(stored) if stored else ""


def validate(
    fields: dict, exact: dict, current: dict, loaded: dict, root: Path, api: Any
) -> None:
    """Check mechanical coordinates and original bytes without semantic source selection."""
    kind = exact["kind"]
    if not isinstance(fields, dict) or set(fields) != set(defaults(kind)):
        raise ValueError("Invalid CR local draft fields")
    if kind == "question":
        if not isinstance(fields["question"], str) or len(fields["question"]) > 4000:
            raise ValueError("CR draft question exceeds the literal question contract")
    elif kind == "navigation":
        read_source(
            current, loaded, root, {"source_ref": exact["source_ref"], **fields}, api
        )
    else:
        identities, offset = fields["input_ids"], fields["offset"]
        if not isinstance(identities, list) or any(
            not isinstance(v, str) for v in identities
        ):
            raise ValueError("Invalid CR source draft identities")
        if identities:
            selected_inputs(loaded, identities)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid CR intake page")


def dispatch(
    action: str,
    args: dict,
    binding: dict,
    loaded: dict,
    root: Path,
    api: Any,
    current: dict,
) -> dict:
    """Recover private drafts under signed selection and CAS; never create public phases."""
    exact = scope(current, loaded, root, args, api)
    identity = "cr-local-draft-" + api.digest(exact)
    path, stored, stamp = snapshot(current, exact, loaded, api)
    if action == "draft_read":
        fields = stored["fields"] if stored else defaults(exact["kind"])
        validate(fields, exact, current, loaded, root, api)
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "selection": {"id": identity},
            "data": {"selection": {"source_ref": exact["source_ref"]}},
            "fields": fields,
            "draft_revision": stamp,
            "can_write": not current["recovery_required"]
            and loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
            "professional_approval": False,
            "model_grant_issued": False,
        }
    if action != "draft_save":
        raise ValueError("Unknown CR local draft action")
    if loaded["run"]["status"] != "running" or "REVIEWER" not in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(","):
        raise PermissionError("CR local drafts require an owned running reviewer run")
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if loaded["run"]["status"] != "running":
            raise PermissionError("CR local draft run is no longer running")
        if current["recovery_required"] or args["revision"] != current["revision"]:
            raise ValueError("Stale or uncertain CR local draft scope")
        exact = scope(current, loaded, root, args, api)
        if args["item_id"] != "cr-local-draft-" + api.digest(exact):
            raise ValueError("Choose the exact CR local draft selection")
        path, stored, stamp = snapshot(current, exact, loaded, api)
        if args["expected_draft_revision"] != stamp:
            raise ValueError("Stale CR local draft checkpoint")
        validate(args["fields"], exact, current, loaded, root, api)
        record = {
            "owner": current["owner"],
            "scope": exact,
            "inputs": loaded["input_manifest"],
            "implementation": current["implementation"],
            "fields": args["fields"],
            "generation": stored["generation"] + 1 if stored else 1,
        }
        api.atomic_json(path, record)
        return {
            "saved": True,
            "draft_revision": api.digest(record),
            "professional_approval": False,
            "model_grant_issued": False,
        }
