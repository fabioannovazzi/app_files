#!/usr/bin/env python3
"""Validate metric-linked commentary and assemble the reviewed draft pack."""

from __future__ import annotations

import argparse
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
    PackContractError,
    finalize_commentary,
    load_json,
    render_html,
    render_markdown,
    sha256_file,
    write_json,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Close metric references and write final reviewable HTML and Markdown."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--commentary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="management-control-pack",
            input_paths=[args.pack, args.commentary],
            output_dir=args.output_dir,
        )
        pack = load_json(args.pack)
        commentary = finalize_commentary(pack, load_json(args.commentary))
    except (AssuranceContractError, PackContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = args.output_dir / "management_control_report.md"
    html_path = args.output_dir / "management_control_dashboard_reviewed.html"
    markdown_path.write_text(render_markdown(pack, commentary), encoding="utf-8")
    html_path.write_text(render_html(pack, commentary), encoding="utf-8")
    receipt = {
        "schema_version": "vera.management_control_commentary_receipt.v1",
        "workflow_id": "management-control-pack",
        "status": "draft_pending_professional_review",
        "pack_sha256": sha256_file(args.pack),
        "commentary_sha256": sha256_file(args.commentary),
        "outputs": [
            {"path": markdown_path.name, "sha256": sha256_file(markdown_path)},
            {"path": html_path.name, "sha256": sha256_file(html_path)},
        ],
        "validation_boundary": (
            "Schema and metric-reference closure were validated; semantic quality, "
            "business causation, and professional approval were not assigned."
        ),
    }
    write_json(args.output_dir / "commentary_receipt.json", receipt)
    LOGGER.info("Wrote reviewed-draft Management Control Pack outputs.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
