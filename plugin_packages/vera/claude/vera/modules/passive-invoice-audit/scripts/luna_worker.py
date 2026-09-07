"""Native Claude/Luna adapter for passive-invoice audit chunks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

__all__ = ["run_luna_chunk", "resolve_worker_selection", "load_worker_selection"]


def load_worker_selection(
    path: Path | None,
    *,
    workflow_id: str,
    reasoning_effort: str | None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Read an explicit reviewed selection, retaining Luna/low when omitted."""
    if path is None:
        return "gpt-5.6-luna", reasoning_effort or "low", None
    return _load_shared_capsule().load_worker_selection(
        path,
        workflow_id=workflow_id,
        reasoning_effort=reasoning_effort,
    )


def resolve_worker_selection(
    *,
    workflow_id: str,
    reasoning_effort: str | None,
    worker_selection: Mapping[str, Any] | None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Use the shared reviewed selection contract without launching a worker."""
    return _load_shared_capsule().resolve_worker_selection(
        workflow_id=workflow_id,
        reasoning_effort=reasoning_effort,
        worker_selection=worker_selection,
    )


def _load_shared_capsule() -> Any:
    roots = [
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3] / "modules",
    ]
    candidates = [
        root / "journal-bank-reconciliation" / "scripts" / "semantic_review.py"
        for root in roots
    ]
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        raise ValueError("Vera's qualified native Luna capsule is unavailable")
    spec = importlib.util.spec_from_file_location("vera_luna_capsule", source)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load Vera's qualified native Luna capsule")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    prior_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_bytecode
    return module


def run_luna_chunk(
    prompt: str,
    output_schema: Mapping[str, Any],
    output_dir: Path,
    workflow_id: str,
    packet_sha256: str,
    reasoning_effort: str,
    *,
    worker_selection: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Run one chunk with Luna or an explicitly reviewed native model selection.

    The shared capsule pins and hashes the Claude executable, uses the existing
    Claude login, supplies prompt content over stdin, enforces structured output,
    and constrains the worker to an ephemeral read-only Seatbelt capsule.  This
    adapter contains no direct model API client and accepts no API key.
    """

    capsule = _load_shared_capsule()
    model, effort, review = (
        capsule.resolve_worker_selection(
            workflow_id=workflow_id,
            reasoning_effort=reasoning_effort,
            worker_selection=worker_selection,
        )
        if worker_selection is not None
        else ("gpt-5.6-luna", reasoning_effort, None)
    )
    result = capsule.run_isolated_luna_worker(
        prompt=prompt,
        output_schema=output_schema,
        output_dir=output_dir,
        workflow_id=workflow_id,
        packet_sha256=packet_sha256,
        reasoning_effort=reasoning_effort,
        **({"worker_selection": review} if review is not None else {}),
    )
    if result.get("model") != model:
        raise ValueError(f"Native Claude worker did not use {model}")
    if result.get("reasoning_effort") != effort:
        raise ValueError("Native Claude worker did not use the requested effort")
    if result.get("selection_review") != review:
        raise ValueError("Native Claude worker selection review does not match")
    return result
