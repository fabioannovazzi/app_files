"""Shared incarico operations for conversation and the native Archive panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from native_archive_navigation import archive_module, engagement_scope, reviewer

__all__ = ["dispatch"]


def dispatch(
    root: Path,
    tool: str,
    args: dict[str, Any],
    independent_work: Callable[[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the selected assignment through its current owned Archive."""
    core = archive_module(root)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    store = core.ledger.incarichi()
    if tool in {"vera_incarico_link_work", "vera_incarico_open_work"}:
        if independent_work is None:
            raise ValueError("Use the native service to resolve the selected work")
        current = store.overview(folder, args["engagement_id"])
        link = next(
            (
                item
                for item in current["work_links"]
                if (item["workflow_id"], item["work_ref"])
                == (args["workflow_id"], args["work_ref"])
            ),
            None,
        )
        resolved = independent_work(args["workflow_id"], args["work_ref"])
        if any(
            key in resolved and resolved[key] != args[key]
            for key in ("client_id", "engagement_id")
        ):
            raise PermissionError(
                "The saved specialist work belongs to another incarico"
            )
        if link and link["binding_identity"] != resolved["binding_identity"]:
            raise ValueError(
                "The saved work binding changed; recover the exact case before reopening"
            )
        if tool == "vera_incarico_open_work":
            if link is None:
                raise ValueError("This work is not linked to the selected incarico")
            return {
                key: value
                for key, value in resolved.items()
                if key != "binding_identity"
            }
        if not reviewer():
            raise PermissionError("This Archive session is read-only")
        retained = {
            "workflow_id": args["workflow_id"],
            "work_ref": args["work_ref"],
            "binding_identity": resolved["binding_identity"],
            "label": args["label"],
        }
        links = [retained if item is link else item for item in current["work_links"]]
        if link is None:
            links.append(retained)
        saved = core.update_studio_incarico(
            args["client_id"],
            args["engagement_id"],
            {**current["fields"], "work_links": links},
            args["expected_revision"],
        )
        return {"saved": True, **saved}
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
            originating_conversation=args.get("originating_conversation"),
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
                primary_format=args.get("primary_format"),
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
            "work_links": overview["work_links"][-20:],
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
