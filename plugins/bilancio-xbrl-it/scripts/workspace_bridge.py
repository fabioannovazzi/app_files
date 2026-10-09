"""Private host-configured Studio Archive bindings for the native workspace."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from access_control import RequestContext, authorize
from case_service import CaseService

__all__ = ["dispatch_workspace"]


def _bindings(context: RequestContext) -> list[dict[str, Any]]:
    configured = os.environ.get("VERA_XBRL_WORKSPACE_BINDINGS", "")
    if not configured:
        raise ValueError(
            "WORKSPACE_SETUP_REQUIRED: configure Studio Archive case bindings"
        )
    path = Path(configured)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128_000:
        raise ValueError(
            "Workspace bindings must be a bounded regular host configuration file"
        )
    payload = json.loads(path.read_bytes())
    if (
        payload["tenant_id"] != context.tenant_id
        or payload["actor_id"] != context.actor_id
    ):
        raise PermissionError(
            "Workspace bindings do not belong to the authenticated actor"
        )
    bindings = payload["bindings"]
    if not isinstance(bindings, list) or len(bindings) > 200:
        raise ValueError("Workspace bindings must contain at most 200 case references")
    if len({item["case_id"] for item in bindings}) != len(bindings):
        raise ValueError("Duplicate workspace case binding")
    return bindings


def _archive_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    # Same sibling module layout in source and the generated Vera package.
    scripts = Path(__file__).resolve().parents[2] / "studio-archive" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from client_ledger import LedgerError, load_run

    try:
        loaded = load_run(
            Path(binding["client_root"]),
            binding["engagement_id"],
            binding["run_id"],
            verify_inputs=False,
        )
    except LedgerError as exc:
        raise ValueError(
            "Studio Archive binding could not be verified; check the configured run"
        ) from exc
    run = loaded["run"]
    if run["client_id"] != binding["client_id"] or run["workflow_id"] != "bilancio-oic":
        raise PermissionError(
            "Workspace case is bound to a different client or workflow"
        )
    return {
        "client_id": run["client_id"],
        "engagement_id": run["engagement_id"],
        "run_id": run["run_id"],
        "label": run["label"],
        "created_at": run["created_at"],
        "run_status": run["status"],
    }


def dispatch_workspace(
    service: CaseService,
    context: RequestContext,
    tool: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Authorize each call against both the host allowlist and the case service."""

    authorize(context, "READ")
    bindings = _bindings(context)
    if tool == "xbrl_workspace_open":
        offset = int(arguments.get("offset", 0))
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        items = []
        for binding in bindings[offset : offset + 30]:
            archive = _archive_binding(binding)
            snapshot = service.workspace_snapshot(
                context, binding["case_id"], "CASE_DASHBOARD"
            )
            items.append(
                {
                    **archive,
                    "case_id": snapshot["case_id"],
                    "revision_id": snapshot["revision_id"],
                    "legal_name": snapshot["legal_name"],
                    "period": snapshot["period"],
                    "state": snapshot["dashboard"]["state"],
                }
            )
        return {
            "cases": items,
            "offset": offset,
            "total": len(bindings),
            "has_more": offset + 30 < len(bindings),
        }
    binding = next(
        (item for item in bindings if item["case_id"] == arguments["case_id"]), None
    )
    if binding is None:
        raise PermissionError("Case is not authorized in this workspace")
    archive = _archive_binding(binding)
    if tool == "xbrl_workspace_review_issue":
        authorize(context, "OVERRIDE")
        if archive["run_status"] != "running":
            raise ValueError("Resume this Studio Archive run before saving decisions")
        if arguments.get("human_reviewed") is not True:
            raise ValueError("An explicit human review action is required")
        result = service.mutate(
            context,
            arguments["case_id"],
            "record_issue_reviews",
            {
                "decisions": [
                    {key: arguments[key] for key in ("issue_id", "action", "reason")}
                ]
            },
            arguments["revision_id"],
            arguments["idempotency_key"],
        )
        # Domain mutation invalidates validation. Show that status rather than
        # silently validating or claiming the case is ready for approval.
        return {"saved": result, "archive": archive}
    snapshot = service.workspace_snapshot(
        context,
        arguments["case_id"],
        arguments.get("view", "ISSUES_PANEL"),
        expected_revision=arguments.get("revision_id"),
        issue_id=arguments.get("issue_id"),
        source_ref=arguments.get("source_ref"),
        offset=int(arguments.get("offset", 0)),
        limit=30,
    )
    snapshot["archive"] = archive
    if tool == "xbrl_workspace_explain":
        if not snapshot["selection"]:
            raise ValueError("Select one current finding first")
        return {
            "context": snapshot["selection"]["model_context"],
            "context_sha256": snapshot["selection"]["context_sha256"],
        }
    return snapshot
