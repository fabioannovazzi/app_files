"""Publish and verify the reviewed media artifact snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from artifact_publication import publish_snapshot, verify_snapshot

__all__ = ["publish_media_generation", "verify_media_generation"]


def publish_media_generation(root: Path, work: Path) -> dict[str, Any]:
    """Publish the complete media output manifest."""
    manifest = json.loads((root / "final_artifacts.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "ready_for_review" or not manifest.get("outputs"):
        raise ValueError("Media publication requires a completed artifact manifest")
    return publish_snapshot(
        root,
        work,
        manifest=manifest,
        records=manifest["outputs"],
        manifest_name="final_artifacts.json",
        pointer_name="current_render.json",
        status="ready_for_review",
    )


def verify_media_generation(root: Path) -> dict[str, Any]:
    """Verify snapshot identity without asserting semantic readiness."""
    return verify_snapshot(
        root,
        pointer_name="current_render.json",
        status="ready_for_review",
        output_field=("outputs",),
    )
