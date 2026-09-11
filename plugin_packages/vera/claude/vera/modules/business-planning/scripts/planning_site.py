"""Prepare the exact validated report as a static Sites source checkout.

Compilation replays source hashes, audience restrictions and calculations. This
helper performs no network operation and does not change sharing permissions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from planning_report import compile_html
from planning_workflow import require

__all__ = ["prepare_site", "main"]
LOGGER = logging.getLogger(__name__)


def prepare_site(
    plan: dict[str, Any], *, source_root: Path, output: Path, audience: str
) -> dict[str, Any]:
    """Validate before writing a fresh, self-contained publication candidate."""
    require(
        audience == plan["case"]["audience"],
        "Site audience differs from the compiled report; prepare the report for the intended readers first",
    )
    rendered = compile_html(plan, source_root=source_root)
    require(
        plan["status"] != "blocked", "A blocked report cannot be prepared for Sites"
    )
    require(
        not output.exists(),
        "Use a fresh Sites output folder; prior versions must not be overwritten",
    )
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    receipt = {
        "schema_version": "mparanza.planning_site.v1",
        "case_id": plan["case"]["case_id"],
        "case_sha256": plan["case_sha256"],
        "content_sha256": plan["content_sha256"],
        "report_sha256": digest,
        "audience": audience,
        "report_status": plan["status"],
        "public_files": ["dist/index.html"],
        "includes_embedded_workpapers": True,
        "publication_status": "prepared_not_published",
        "refresh": "explicit_recompile_and_publish",
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


def main(argv: list[str] | None = None) -> int:
    """Prepare a persisted report for the audience selected by the operator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audience", required=True)
    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        prepare_site(
            plan,
            source_root=args.source_root,
            output=args.output_dir,
            audience=args.audience,
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    LOGGER.info("Prepared report for Sites: %s", args.output_dir)
    return 0
