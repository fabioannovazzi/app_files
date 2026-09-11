"""Write the shared local management report and exact execution receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from management_control_core import (
    COMMENTARY_SCHEMA,
    build_model_context,
    build_model_context_receipt,
    render_html,
    render_markdown,
    sha256_file,
    write_excel,
    write_json,
)

__all__ = ["write_pack_outputs"]


def write_pack_outputs(
    pack: dict[str, Any], *, inputs: list[Path], recipe_path: Path, output_dir: Path
) -> None:
    """Persist the calculated facts, bounded model context and report artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = output_dir / "management_control_pack.json"
    write_json(pack_path, pack)
    model_context = build_model_context(pack)
    write_json(output_dir / "model_context.json", model_context)
    write_json(
        output_dir / "model_context_receipt.json",
        build_model_context_receipt(pack, model_context),
    )
    (output_dir / "management_control_facts.md").write_text(
        render_markdown(pack), encoding="utf-8"
    )
    (output_dir / "management_control_dashboard.html").write_text(
        render_html(pack), encoding="utf-8"
    )
    write_excel(output_dir / "management_control_pack.xlsx", pack)
    pack_sha256 = sha256_file(pack_path)
    commentary_template = {
        "schema_version": COMMENTARY_SCHEMA,
        "workflow_id": "management-control-pack",
        "pack_sha256": pack_sha256,
        "observations": [],
        "hypotheses": [],
        "questions": [],
        "limitations": [],
    }
    write_json(output_dir / "commentary_template.json", commentary_template)
    output_names = (
        "management_control_pack.json",
        "model_context.json",
        "model_context_receipt.json",
        "management_control_facts.md",
        "management_control_dashboard.html",
        "management_control_pack.xlsx",
        "commentary_template.json",
    )
    receipt = {
        "schema_version": "vera.management_control_execution_receipt.v1",
        "workflow_id": "management-control-pack",
        "status": pack["status"],
        "recipe_sha256": sha256_file(recipe_path),
        "inputs": [
            {
                "input_id": f"input_{index:03d}",
                "sha256": sha256_file(path),
                "byte_count": path.stat().st_size,
            }
            for index, path in enumerate(inputs, start=1)
        ],
        "outputs": [
            {
                "path": name,
                "sha256": sha256_file(output_dir / name),
                "byte_count": (output_dir / name).stat().st_size,
            }
            for name in output_names
        ],
        "implementation_reason": (
            "Exact arithmetic, period membership after reviewed mappings, aging buckets, "
            "and output hashes are deterministic because they are mechanically verifiable."
        ),
    }
    receipt["content_sha256"] = hashlib.sha256(
        (
            json.dumps(
                receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    write_json(output_dir / "execution_receipt.json", receipt)
