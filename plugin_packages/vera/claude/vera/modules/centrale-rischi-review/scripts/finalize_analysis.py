#!/usr/bin/env python3
"""Validate evidence-linked commentary and assemble the reviewed draft."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break

from centrale_rischi_core import (  # noqa: E402
    CentraleRischiContractError,
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
    """Close evidence references and write final reviewable outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--commentary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="centrale-rischi-review",
            input_paths=[args.analysis, args.commentary],
            output_dir=args.output_dir,
        )
        analysis = load_json(args.analysis)
        commentary = finalize_commentary(analysis, load_json(args.commentary))
    except (
        AssuranceContractError,
        CentraleRischiContractError,
        OSError,
        ValueError,
    ) as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = args.output_dir / "centrale_rischi_report.md"
    html_path = args.output_dir / "centrale_rischi_dashboard_reviewed.html"
    markdown_path.write_text(render_markdown(analysis, commentary), encoding="utf-8")
    html_path.write_text(render_html(analysis, commentary), encoding="utf-8")
    write_json(
        args.output_dir / "commentary_receipt.json",
        {
            "schema_version": "vera.centrale_rischi_commentary_receipt.v1",
            "workflow_id": "centrale-rischi-review",
            "status": "draft_pending_professional_review",
            "analysis_sha256": sha256_file(args.analysis),
            "commentary_sha256": sha256_file(args.commentary),
            "outputs": [
                {"path": markdown_path.name, "sha256": sha256_file(markdown_path)},
                {"path": html_path.name, "sha256": sha256_file(html_path)},
            ],
            "validation_boundary": "Schema and evidence-reference closure were validated; source meaning, materiality, credit judgment and professional approval were not assigned.",
        },
    )
    LOGGER.info("Wrote reviewed-draft Centrale Rischi outputs.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
