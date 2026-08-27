#!/usr/bin/env python3
"""Calculate and render one reviewed Vera Management Control Pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break

from management_control_core import (  # noqa: E402
    COMMENTARY_SCHEMA,
    PackContractError,
    build_management_pack,
    build_model_context,
    build_model_context_receipt,
    load_json,
    load_source_tables,
    render_html,
    render_markdown,
    sha256_file,
    write_excel,
    write_json,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run exact calculations and write the normal management-pack outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="management-control-pack",
            input_paths=[*args.input, args.recipe],
            output_dir=args.output_dir,
        )
        tables = load_source_tables(args.input)
        recipe = load_json(args.recipe)
        pack = build_management_pack(tables, recipe)
    except (AssuranceContractError, PackContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = args.output_dir / "management_control_pack.json"
    write_json(pack_path, pack)
    model_context = build_model_context(pack)
    write_json(args.output_dir / "model_context.json", model_context)
    write_json(
        args.output_dir / "model_context_receipt.json",
        build_model_context_receipt(pack, model_context),
    )
    (args.output_dir / "management_control_facts.md").write_text(
        render_markdown(pack), encoding="utf-8"
    )
    (args.output_dir / "management_control_dashboard.html").write_text(
        render_html(pack), encoding="utf-8"
    )
    write_excel(args.output_dir / "management_control_pack.xlsx", pack)
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
    write_json(args.output_dir / "commentary_template.json", commentary_template)
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
        "recipe_sha256": sha256_file(args.recipe),
        "inputs": [
            {
                "input_id": f"input_{index:03d}",
                "sha256": sha256_file(path),
                "byte_count": path.stat().st_size,
            }
            for index, path in enumerate(args.input, start=1)
        ],
        "outputs": [
            {
                "path": name,
                "sha256": sha256_file(args.output_dir / name),
                "byte_count": (args.output_dir / name).stat().st_size,
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
    write_json(args.output_dir / "execution_receipt.json", receipt)
    LOGGER.info("Wrote Management Control Pack with status %s.", pack["status"])
    return 0 if pack["status"] != "blocked" else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
