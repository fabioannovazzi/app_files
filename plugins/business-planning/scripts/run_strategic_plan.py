#!/usr/bin/env python3
"""Finalize and render one reviewed Clara strategic business-planning case."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from business_planning_contribution import (  # noqa: E402
    BusinessPlanningContributionError,
    attach_counterpart_contribution,
    review_counterpart_contribution,
    write_assumption_register,
)
from strategic_planning_core import (  # noqa: E402
    StrategicPlanningContractError,
    build_counterpart_contribution,
    build_model_context,
    build_strategic_plan,
    load_json,
    render_html,
    render_markdown,
    validate_case_workspace_boundary,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _canonical_json_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Validate the strategic case and write the normal review package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--case-workspace", required=True, type=Path)
    parser.add_argument("--counterpart-contribution", type=Path)
    args = parser.parse_args(argv)
    counterpart_review: dict[str, object] | None = None
    counterpart_contribution: dict[str, object] | None = None
    try:
        validate_case_workspace_boundary(
            args.case,
            args.output_dir,
            args.case_workspace,
            additional_inputs=(
                (args.counterpart_contribution,)
                if args.counterpart_contribution is not None
                else ()
            ),
        )
        case = load_json(args.case)
        if args.counterpart_contribution is not None:
            counterpart_contribution = load_json(args.counterpart_contribution)
            counterpart_review = review_counterpart_contribution(
                case,
                counterpart_contribution,
                receiving_product="Clara",
            )
        plan = build_strategic_plan(case)
        if counterpart_contribution is not None and counterpart_review is not None:
            plan = attach_counterpart_contribution(
                plan,
                counterpart_contribution,
                counterpart_review,
            )
    except (
        BusinessPlanningContributionError,
        StrategicPlanningContractError,
        OSError,
        ValueError,
    ) as exc:
        parser.error(str(exc))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.output_dir / "strategic_business_plan.json"
    _write_json(plan_path, plan)
    _write_json(args.output_dir / "model_context.json", build_model_context(plan))
    _write_json(
        args.output_dir / "counterpart_contribution.json",
        build_counterpart_contribution(plan),
    )
    if counterpart_review is not None:
        _write_json(
            args.output_dir / "counterpart_contribution_review.json",
            counterpart_review,
        )
    write_assumption_register(
        args.output_dir / "assumption_ledger.csv", plan["assumption_register"]
    )
    (args.output_dir / "strategic_business_plan.md").write_text(
        render_markdown(plan), encoding="utf-8"
    )
    (args.output_dir / "strategic_business_plan_review.html").write_text(
        render_html(plan), encoding="utf-8"
    )

    output_names = [
        "strategic_business_plan.json",
        "strategic_business_plan.md",
        "strategic_business_plan_review.html",
        "model_context.json",
        "assumption_ledger.csv",
        "counterpart_contribution.json",
    ]
    if counterpart_review is not None:
        output_names.append("counterpart_contribution_review.json")
    receipt: dict[str, object] = {
        "schema_version": "mparanza.business_planning_strategic_execution_receipt.v3",
        "workflow_id": "business-planning",
        "professional_lens": "strategic_commercial",
        "status": plan["status"],
        "review_status": plan["review_status"],
        "case_sha256": _sha256_file(args.case),
        "case_content_sha256": _canonical_json_sha256(case),
        "counterpart_contribution": (
            {
                "path": args.counterpart_contribution.name,
                "sha256": _sha256_file(args.counterpart_contribution),
                "review_status": counterpart_review["status"],
                "included_in_owner_plan": plan["counterpart_contribution"][
                    "included_in_owner_plan"
                ],
            }
            if args.counterpart_contribution is not None
            and counterpart_review is not None
            else None
        ),
        "outputs": [
            {
                "path": name,
                "sha256": _sha256_file(args.output_dir / name),
                "byte_count": (args.output_dir / name).stat().st_size,
            }
            for name in output_names
        ],
        "implementation_reason": (
            "Schema, identifier and reference closure, rendering, and artifact hashes "
            "are deterministic because they are mechanically verifiable. Strategic "
            "meaning, option design, recommendation, and cross-lens agreement remain "
            "model-led and professional."
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
    _write_json(args.output_dir / "execution_receipt.json", receipt)
    LOGGER.info(
        "Wrote strategic Business Planning package with status %s.", plan["status"]
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
