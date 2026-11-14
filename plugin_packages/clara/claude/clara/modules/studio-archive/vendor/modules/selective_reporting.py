"""Fixed Vera report scope and mechanically checked Archive run bindings."""

from __future__ import annotations

__all__ = ["REPORT_PIPELINES", "report_pipeline"]

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
