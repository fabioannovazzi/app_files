"""Resolve portable workflow identity for local execution diagnostics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["load_workflow_context"]


def load_workflow_context(path: Path, *, workflow_id: str | None) -> dict[str, Any]:
    """Reuse Archive's verified hydration instead of assuming stored absolute paths."""
    context = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(context, dict):
        raise ValueError("Workflow diagnostic context must be an object")
    if context.get("schema_version") not in {
        "vera.client_workflow_context.v2",
        "vera.standalone_workflow_context.v1",
    }:
        return context
    root = Path(__file__).resolve().parents[1]
    for vendor in (root / "vendor/modules", root.parent / "_shared/vendor/modules"):
        if (vendor / "vera_assurance").is_dir():
            if str(vendor) not in sys.path:
                sys.path.insert(0, str(vendor))
            break
    from vera_assurance import load_client_engagement_context_file

    # Identity and path equality prevent attributing another run's diagnostics.
    return load_client_engagement_context_file(
        path,
        expected_workflow_id=workflow_id or "",
        allowed_statuses=(
            "running",
            "ready_for_review",
            "completed",
            "failed",
            "cancelled",
        ),
    )
