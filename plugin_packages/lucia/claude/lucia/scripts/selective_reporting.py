"""Fixed Vera report scope and mechanically checked Archive run bindings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["REPORT_PIPELINES", "report_pipeline", "bind_report_run", "has_comparison"]

# Product scope is explicit, not a semantic classifier. Aliases identify existing
# component entrypoints; notably client-file-preparation is NOT an XML-check run.
REPORT_PIPELINES = frozenset(
    {
        "journal-bank-reconciliation",
        "open-item-reconciliation",
        "journal-sampling",
        "vouching",
        "fatture-xml-check",
        "purchase-invoice-review",
        "centrale-rischi-review",
        "financial-report-builder",
        "report-enti-locali",
        "management-control-pack",
        "variance-analysis",
        "agenzia-acquisition",
        "archive-organization",
    }
)
_ALIASES = {
    "check-entries": "vouching",
    "passive-invoice-audit": "purchase-invoice-review",
    "report-builder": "financial-report-builder",
}


def report_pipeline(workflow_id: str) -> str | None:
    """Return the explicitly selected pipeline, never infer it from task text."""
    pipeline = _ALIASES.get(workflow_id, workflow_id)
    return pipeline if pipeline in REPORT_PIPELINES else None


def bind_report_run(output: Path, workflow_id: str, run_id: str) -> dict[str, Any]:
    """Require the exact active Archive output and validated source receipts."""
    from vera_assurance.contracts import (
        AssuranceContractError,
        load_client_engagement_context_file,
    )

    if report_pipeline(workflow_id) is None:
        raise AssuranceContractError("This Vera pipeline is outside the report scope")
    context = load_client_engagement_context_file(
        output.parent / "context.json",
        expected_workflow_id=workflow_id,
        allowed_statuses=("running", "ready_for_review", "failed", "cancelled"),
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise AssuranceContractError("Selective reports require a Studio Archive run")
    if (
        context["workflow_id"] != workflow_id
        or context["run_id"] != run_id
        or Path(context["output_dir"]) != output.resolve()
    ):
        raise AssuranceContractError(
            "Report identity/output does not match the Archive run"
        )
    return context


def has_comparison(request: Mapping[str, Any]) -> bool:
    """Require a positive measured population and an evidenced local remainder.

    Counts come from execution evidence, never from the privacy description.
    This checks their shape; it cannot prove host reads were recorded completely.
    """
    # Without population identities we cannot disambiguate a later complete read
    # from an earlier local-only phase. Conservatively suppress that comparison.
    if any(
        phase.get("outcome") in {"not_measurable", "full_context_required"}
        for phase in request.get("phases", [])
    ):
        return False
    units = {
        "rows",
        "columns",
        "cells",
        "files",
        "pages",
        "items",
        "bytes",
        "characters",
    }
    for phase in request.get("phases", []):
        if not isinstance(phase, Mapping) or not phase.get("evidence_files"):
            continue
        source = {
            item["unit"]
            for item in phase.get("source_extent", [])
            if item.get("unit") in units
            and item.get("basis") in {"measured", "derived"}
            and isinstance(item.get("quantity"), (int, float))
            and not isinstance(item["quantity"], bool)
            and item["quantity"] > 0
        }
        if any(
            item.get("unit") in source
            and item.get("basis") in {"measured", "derived"}
            and isinstance(item.get("quantity"), (int, float))
            and not isinstance(item["quantity"], bool)
            and item["quantity"] > 0
            for item in phase.get("remained_local", [])
        ):
            return True
    return False
