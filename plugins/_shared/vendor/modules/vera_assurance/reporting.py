"""Connect a maintained worker boundary to its exact active Archive execution."""

from __future__ import annotations

import sys
from pathlib import Path

from .contracts import load_client_engagement_context_file

__all__ = ["record_model_submission"]


def record_model_submission(
    output: Path, *, prompt: str, model: str, workflow_id: str
) -> None:
    """Retain the exact submitted prompt locally; never send it to the receipt service."""
    context_path = next(
        (
            parent / "context.json"
            for parent in (output, *output.parents)
            if (parent / "context.json").is_file() and (parent / "run.json").is_file()
        ),
        None,
    )
    if context_path is None:
        return  # Standalone engine/qualification tests are not Archive runs.
    context = load_client_engagement_context_file(
        context_path, expected_workflow_id=workflow_id
    )
    if not output.resolve().is_relative_to(Path(context["output_dir"])):
        raise ValueError("Worker output belongs to another Archive execution")
    roots = [parent / "scripts" for parent in Path(__file__).resolve().parents]
    roots.extend(
        parent / "vera/scripts"
        for parent in Path(__file__).resolve().parents
        if parent.name == "plugins"
    )
    scripts = next(
        (root for root in roots if (root / "archive_reporting.py").is_file()), None
    )
    if scripts is None:
        raise ValueError("Automatic Archive reporting runtime is unavailable")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import secrets

    from archive_report_store import RunStore
    from archive_reporting import observe_tool

    root = context_path.parent
    if RunStore(root).state() is None:
        raise ValueError(
            "Worker submission requires the Archive start reporting record"
        )
    observe_tool(
        root,
        {
            "session_id": "worker",
            "tool_use_id": secrets.token_hex(24),
            "tool_name": "model_worker:" + model,
            "tool_input": {},
            "tool_response": prompt,
            "evidence_basis": "submitted_worker_prompt",
        },
    )
