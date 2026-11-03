"""Receipt-verified report bytes for the native MCP App; no browser server."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "vendor/modules", ROOT.parent / "_shared/vendor/modules"):
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break
from vera_assurance import load_client_engagement_context_file

__all__ = ["report_bytes", "preview_document"]
REPORT = "management_control_dashboard_reviewed.html"


def report_bytes(context: Path, report: Path) -> bytes:
    """Read the exact declared report; no full pack enters model context."""
    receipt = report.parent / "commentary_receipt.json"
    if report.name != REPORT:
        raise ValueError("Select the current reviewed-draft management dashboard")
    load_client_engagement_context_file(
        context,
        expected_workflow_id="management-control-pack",
        input_paths=[report, receipt],
        allowed_statuses=("running", "ready_for_review", "completed"),
    )
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if (
        data.get("schema_version") != "vera.management_control_commentary_receipt.v1"
        or data.get("workflow_id") != "management-control-pack"
        or data.get("status") != "draft_pending_professional_review"
    ):
        raise ValueError("A native reviewed-draft commentary receipt is required")
    entries = [row for row in data["outputs"] if row["path"] == REPORT]
    content = report.read_bytes()
    if len(entries) != 1 or hashlib.sha256(content).hexdigest() != entries[0]["sha256"]:
        raise ValueError("The report no longer matches its native receipt")
    return content


def preview_document(context: Path, report: Path) -> str:
    """Allow only the producer's pinned month-switching script in an opaque frame."""
    content = report_bytes(context, report).decode("utf-8")
    script = (ROOT / "assets/budget-report.js").read_bytes()
    script_hash = base64.b64encode(hashlib.sha256(script).digest()).decode("ascii")
    csp = (
        "default-src 'none'; script-src 'sha256-"
        + script_hash
        + "'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"
    )
    policy = '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
    # Put the policy before any executable report content.
    return policy + content
