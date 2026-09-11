"""Replay one reviewed management report before preparing its Sites source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from management_control_core import (
    PackContractError,
    build_management_pack,
    finalize_commentary,
    load_source_tables,
    render_html,
)

__all__ = ["prepare_site"]


def prepare_site(
    *,
    inputs: list[Path],
    recipe: dict[str, Any],
    pack: dict[str, Any],
    output: Path,
    audience: str,
    commentary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate source replay and audience before writing a fresh publication candidate."""
    rebuilt = build_management_pack(load_source_tables(inputs), recipe)
    if rebuilt != pack:
        raise PackContractError(
            "Pack differs from the current source replay; rerun and review the report."
        )
    if pack["status"] == "blocked":
        raise PackContractError("A blocked report cannot be prepared for Sites.")
    if audience != pack["audience"]:
        raise PackContractError(
            "Site audience differs from the reviewed report audience."
        )
    if not pack["sections"]["budget_variance"].get("comparison_rows"):
        raise PackContractError(
            "No supported budget comparison is available for this report."
        )
    if output.exists():
        raise PackContractError(
            "Use a fresh Sites output folder; preserve earlier reports."
        )
    checked = finalize_commentary(pack, commentary) if commentary is not None else None
    rendered = render_html(pack, checked)
    receipt = {
        "schema_version": "mparanza.management_site.v1",
        "entity": pack["entity"],
        "audience": audience,
        "inventory_sha256": pack["inventory_sha256"],
        "recipe_sha256": pack["recipe_sha256"],
        "report_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "report_status": pack["report_status"],
        "coverage_status": pack["status"],
        "public_files": ["dist/index.html"],
        "includes_all_comparison_views": True,
        "includes_raw_source_files": False,
        "publication_status": "prepared_not_published",
        "refresh": "explicit_replay_and_publish",
    }
    (output / "dist").mkdir(parents=True)
    (output / "dist/index.html").write_text(rendered, encoding="utf-8")
    (output / ".openai").mkdir()
    (output / ".openai/hosting.json").write_text(
        json.dumps({"static": {"directory": "dist"}}, indent=2) + "\n", encoding="utf-8"
    )
    (output / "site_delivery.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt
