"""Shared incarico operations for conversation and the native Archive panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from native_archive_navigation import archive_module, engagement_scope, reviewer

__all__ = ["dispatch"]


def dispatch(root: Path, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Resolve the selected assignment through its current owned Archive."""
    core = archive_module(root)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    store = core.ledger.incarichi()
    if tool == "vera_incarico_map_legacy":
        if not reviewer():
            raise PermissionError("This Archive session is read-only")
        return core.map_studio_legacy_incarichi(
            args["client_id"], args["engagement_id"], args["targets"]
        )
    if tool == "vera_incarico_begin":
        if not reviewer():
            raise PermissionError("This Archive session is read-only")
        return core.begin_studio_incarico(
            args["client_id"],
            args["engagement_id"],
            args["workflow_id"],
            args["purpose"],
        )
    if tool in {"vera_incarico_publish_result", "vera_incarico_reuse_result"}:
        if not reviewer():
            raise PermissionError("This Archive session is read-only")
        if tool == "vera_incarico_publish_result":
            return core.publish_studio_incarico_result(
                args["client_id"],
                args["engagement_id"],
                args["entry_key"],
                args["label"],
                args["files"],
                args["expected_revision"],
                args["idempotency_key"],
            )
        return core.reuse_studio_incarico_result(
            args["client_id"], args["engagement_id"], args["origin"], args["role"]
        )
    if tool == "vera_incarico_update":
        if not reviewer():
            raise PermissionError("This Archive session is read-only")
        saved = core.update_studio_incarico(
            args["client_id"],
            args["engagement_id"],
            args["fields"],
            args["expected_revision"],
        )
        return {"saved": True, **saved}
    if tool == "vera_incarico_document":
        return core.read_studio_incarico_document(
            args["client_id"], args["engagement_id"], args["reference"]
        )
    if tool not in {"vera_incarico_read", "vera_incarico_context"}:
        raise ValueError("Unknown incarico operation")
    overview = store.overview(folder, args["engagement_id"])
    if tool == "vera_incarico_context":
        runs = core.ledger.inspect_runs(
            folder, args["engagement_id"], verify_inputs=False
        )
        return {
            "client_id": engagement["client_id"],
            "engagement_id": args["engagement_id"],
            "label": engagement["label"],
            "purpose": overview["purpose"],
            "workflow_id": overview["workflow_id"],
            "revision": overview["revision"],
            "continuation": overview["continuation"],
            "results": overview["results"][-20:],
            "deliverables": [
                {
                    "entry_key": entry["entry_key"],
                    "label": entry["label"],
                    "current_revision": entry["current_revision"],
                    "current_version": entry["versions"][-1],
                    "history_count": len(entry["versions"]) - 1,
                }
                for entry in overview["deliverables"][-20:]
            ],
            "documents": overview["documents"][-30:],
            "document_total": len(overview["documents"]),
            "runs": [
                {
                    key: run["run"][key]
                    for key in ("run_id", "workflow_id", "status", "label")
                }
                for run in runs["runs"][-20:]
            ],
            "run_total": len(runs["runs"]),
            "historical_assignments": overview["historical_assignments"][-20:],
            "legacy_assignments": overview["legacy_assignments"][-20:],
            "conversations": overview["conversations"][-20:],
            "issues": overview["document_issues"]
            + overview["deliverable_issues"]
            + runs["collection_issues"],
        }
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid document page")
    documents = overview["documents"]
    return {
        **overview,
        "documents": documents[offset : offset + 30],
        "offset": offset,
        "total": len(documents),
        "has_more": offset + 30 < len(documents),
    }
