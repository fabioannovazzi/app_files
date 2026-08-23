"""Native Codex/Luna adapter for passive-invoice audit chunks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

__all__ = ["run_luna_chunk"]


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
) -> Mapping[str, Any]:
    """Run one chunk with exactly gpt-5.6-luna through native Codex exec.

    The shared capsule pins and hashes the Codex executable, uses the existing
    Codex login, supplies prompt content over stdin, enforces structured output,
    and constrains the worker to an ephemeral read-only Seatbelt capsule.  This
    adapter contains no direct model API client and accepts no API key.
    """

    capsule = _load_shared_capsule()
    result = capsule.run_isolated_luna_worker(
        prompt=prompt,
        output_schema=output_schema,
        output_dir=output_dir,
        workflow_id=workflow_id,
        packet_sha256=packet_sha256,
        reasoning_effort=reasoning_effort,
    )
    if result.get("model") != "gpt-5.6-luna":
        raise ValueError("Native Codex worker did not use gpt-5.6-luna")
    if result.get("reasoning_effort") != reasoning_effort:
        raise ValueError("Native Codex worker did not use the requested effort")
    return result
