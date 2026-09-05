"""Shared command execution; entry products differ only in workspace binding."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from business_planning_core import load_json
from planning_report import write_package
from planning_workflow import CASE_SCHEMA, PlanningError, build_plan, require
from strategic_planning_core import validate_case_workspace_boundary
from vera_assurance import load_client_engagement_context_file

__all__ = ["run"]
LOGGER = logging.getLogger(__name__)


def run(owner: str, argv: list[str] | None = None) -> int:
    """Bind all selected sources to the owner workspace, then run one compiler."""
    parser = argparse.ArgumentParser(
        description=f"{owner}-owned shared Business Planning"
    )
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--client-engagement", type=Path, required=owner == "Vera")
    parser.add_argument("--case-workspace", type=Path, required=owner == "Clara")
    parser.add_argument("--counterpart-contribution", type=Path)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args(argv)
    try:
        if owner == "Clara":
            validate_case_workspace_boundary(
                args.case, args.output_dir, args.case_workspace
            )
        case = load_json(args.case)
        require(
            case.get("schema_version") == CASE_SCHEMA,
            "Finalization requires the shared v2 case with provenance; legacy cases must be reviewed and migrated",
        )
        require(
            args.counterpart_contribution is None,
            "Review internal contributions into the shared v2 register; independent counterpart files cannot finalize a plan",
        )
        source_root = args.source_root or args.case.parent
        sources = [
            (source_root / source["path"]).resolve() for source in case["sources"]
        ]
        if owner == "Vera":
            load_client_engagement_context_file(
                args.client_engagement,
                expected_workflow_id="business-planning",
                input_paths=[args.case, *sources],
                output_dir=args.output_dir,
            )
        else:
            validate_case_workspace_boundary(
                args.case,
                args.output_dir,
                args.case_workspace,
                additional_inputs=sources,
            )
        plan = build_plan(case, owner=owner, source_root=source_root)
        write_package(
            plan, source_root=source_root, output=args.output_dir, pdf=args.pdf
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    LOGGER.info("Wrote %s Business Planning report: %s", owner, plan["status"])
    return 0 if plan["status"] == "ready_for_professional_review" else 2
