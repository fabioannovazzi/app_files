#!/usr/bin/env python3
"""Calculate and render one reviewed Vera financial business-planning case."""

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

from business_planning_core import (  # noqa: E402
    COMMENTARY_SCHEMA,
    BusinessPlanningContractError,
    build_business_plan,
    build_counterpart_handoff,
    build_model_context,
    load_json,
    render_html,
    render_markdown,
    write_assumption_ledger,
    write_excel,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    canonical_json_sha256,
    load_client_engagement_context_file,
    write_json,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Run exact planning calculations and write the normal review package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="business-planning",
            input_paths=[args.case],
            output_dir=args.output_dir,
        )
        case = load_json(args.case)
        plan = build_business_plan(case)
    except (
        AssuranceContractError,
        BusinessPlanningContractError,
        OSError,
        ValueError,
    ) as exc:
        parser.error(str(exc))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.output_dir / "business_plan.json"
    write_json(plan_path, plan)
    write_json(args.output_dir / "reconciliation.json", plan["reconciliation"])
    write_json(args.output_dir / "model_context.json", build_model_context(plan))
    write_json(
        args.output_dir / "business_planning_handoff.json",
        build_counterpart_handoff(plan),
    )
    write_assumption_ledger(args.output_dir / "assumption_ledger.csv", plan)
    write_excel(args.output_dir / "business_plan.xlsx", plan)
    (args.output_dir / "business_plan_facts.md").write_text(
        render_markdown(plan), encoding="utf-8"
    )
    (args.output_dir / "business_plan_review.html").write_text(
        render_html(plan), encoding="utf-8"
    )

    commentary_template = {
        "schema_version": COMMENTARY_SCHEMA,
        "workflow_id": "business-planning",
        "plan_sha256": _sha256_file(plan_path),
        "calculated_observations": [],
        "hypotheses": [],
        "questions": [],
        "risks": [],
        "limitations": [],
        "professional_decisions": [],
    }
    write_json(args.output_dir / "commentary_template.json", commentary_template)

    output_names = (
        "business_plan.json",
        "business_plan.xlsx",
        "assumption_ledger.csv",
        "reconciliation.json",
        "model_context.json",
        "commentary_template.json",
        "business_plan_facts.md",
        "business_plan_review.html",
        "business_planning_handoff.json",
    )
    receipt = {
        "schema_version": "mparanza.business_planning_financial_execution_receipt.v1",
        "workflow_id": "business-planning",
        "status": plan["status"],
        "review_status": plan["review_status"],
        "case_sha256": _sha256_file(args.case),
        "case_content_sha256": canonical_json_sha256(case),
        "outputs": [
            {
                "path": name,
                "sha256": _sha256_file(args.output_dir / name),
                "byte_count": (args.output_dir / name).stat().st_size,
            }
            for name in output_names
        ],
        "implementation_reason": (
            "Canonical Decimal arithmetic, statement roll-forwards, reference closure, "
            "reconciliation, and artifact hashes are deterministic because they are "
            "mechanically verifiable and must replay exactly."
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
    LOGGER.info("Wrote Business Planning package with status %s.", plan["status"])
    return 2 if plan["status"] == "blocked" else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
