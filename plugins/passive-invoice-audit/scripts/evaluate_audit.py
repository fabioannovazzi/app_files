"""Evaluate passive-invoice audit results or create synthetic test packets."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from audit_core import (
    AuditConfig,
    create_synthetic_population,
    evaluate_results,
    evaluate_synthetic_population,
)
from cowork_worker import configured_runtime, run_cowork_chunk
from luna_worker import run_luna_chunk
from vera_assurance import (
    AssuranceContractError,
    load_client_workflow_context_for_output,
    validate_client_workflow_run,
)

__all__ = ["main"]


def main() -> int:
    """Run the selected evaluation operation."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--results", type=Path, required=True)
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    synthetic = subparsers.add_parser("synthetic")
    synthetic.add_argument("--results", type=Path, required=True)
    synthetic.add_argument("--mutation-plan", type=Path, required=True)
    synthetic.add_argument("--output", type=Path, required=True)
    synthetic_evaluate = subparsers.add_parser("synthetic-evaluate")
    synthetic_evaluate.add_argument("--results", type=Path, required=True)
    synthetic_evaluate.add_argument("--mutation-plan", type=Path, required=True)
    synthetic_evaluate.add_argument("--output", type=Path, required=True)
    synthetic_evaluate.add_argument("--chunk-size", type=int, default=25)
    synthetic_evaluate.add_argument("--concurrency", type=int, default=2)
    synthetic_evaluate.add_argument("--max-retries", type=int, default=2)
    synthetic_evaluate.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="low",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    auxiliary_input = args.labels if args.command == "evaluate" else args.mutation_plan
    try:
        client_context = load_client_workflow_context_for_output(
            args.results,
            expected_workflow_id="passive-invoice-audit",
            input_paths=[auxiliary_input],
        )
        validate_client_workflow_run(
            client_context,
            expected_workflow_id="passive-invoice-audit",
            input_paths=[args.results, auxiliary_input],
            output_dir=args.output,
        )
    except AssuranceContractError as exc:
        logging.getLogger(__name__).error("CLIENT_ENGAGEMENT_BLOCKED: %s", exc)
        return 2

    if args.command == "evaluate":
        report = evaluate_results(args.results, args.labels, args.output)
        logging.getLogger(__name__).info(
            "%s", json.dumps(report, indent=2, ensure_ascii=False)
        )
    elif args.command == "synthetic":
        generated = create_synthetic_population(
            args.results, args.mutation_plan, args.output
        )
        logging.getLogger(__name__).info(
            "%s", json.dumps({"synthetic_packets": len(generated)}, indent=2)
        )
    else:
        cowork = configured_runtime() == "cowork-haiku"
        report = evaluate_synthetic_population(
            args.results,
            args.mutation_plan,
            args.output,
            run_cowork_chunk if cowork else run_luna_chunk,
            AuditConfig(
                semantic_model="haiku" if cowork else "gpt-5.6-luna",
                chunk_size=args.chunk_size,
                concurrency=args.concurrency,
                max_retries=args.max_retries,
                reasoning_effort=args.reasoning_effort,
            ),
        )
        logging.getLogger(__name__).info(
            "%s", json.dumps(report, indent=2, ensure_ascii=False)
        )
        if report["status"] == "awaiting_semantic_review":
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
