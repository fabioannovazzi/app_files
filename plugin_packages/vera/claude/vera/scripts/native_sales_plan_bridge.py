"""Isolated calls to the maintained Sales Plan runner and implementation identity."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Execute only the existing run command; no model or business rules are added."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    from run_plan import IMPLEMENTATION_FILES
    from run_plan import main as run_cli

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        result = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in IMPLEMENTATION_FILES
        }
    elif request["operation"] == "contract":
        import prepare_sales_plan_case as plan

        result = {
            "schema": plan.CASE_SCHEMA,
            "recipe": plan.RECIPE_ID,
            "engine_version": plan.ENGINE_VERSION,
            "required_metrics": list(plan.REQUIRED_METRICS),
            "optional_metrics": list(plan.OPTIONAL_METRICS),
            "drivers": list(plan.DRIVER_ORDER),
            "behaviors": sorted(plan.DEFAULT_BEHAVIORS),
            "overlaps": sorted(plan.SAME_DRIVER_OVERLAP_BEHAVIORS),
            "bases": sorted(plan.ASSUMPTION_BASES),
            "source_scenario": plan.SOURCE_SCENARIO,
            "target_scenario": plan.TARGET_SCENARIO,
            "time_profile": plan.TIME_PROFILE,
            "fx_definition": plan.FX_RATE_DEFINITION,
        }
    elif request["operation"] == "query":
        from model_use import ModelUseError, extract_scenario_rows
        from vera_assurance import load_client_engagement_context_file

        manifest = Path(request["manifest"])
        load_client_engagement_context_file(
            Path(request["context"]),
            expected_workflow_id="sales-plan",
            input_paths=[manifest, manifest.parent / "sales_plan_scenario.csv"],
            output_dir=manifest.parent,
        )
        try:
            result = extract_scenario_rows(
                manifest_path=manifest,
                reason=request["reason"],
                source_row_ids=request["source_row_ids"],
                where=request["where"],
                columns=request["columns"],
            )
        except ModelUseError as exc:
            result = {"ok": False, "error": str(exc)}
    elif request["operation"] == "run_draft":
        from plan_contract_kernel import ContractValidationError
        from prepare_sales_plan_case import declared_actual_sales_path
        from run_plan import run_plan
        from vera_assurance import (
            load_client_engagement_context_file,
            validate_client_workflow_run,
        )

        case = Path(request["case"])
        output = Path(request["output"])
        context = load_client_engagement_context_file(
            Path(request["context"]),
            expected_workflow_id="sales-plan",
            input_paths=[case],
            output_dir=output,
        )
        validate_client_workflow_run(
            context,
            expected_workflow_id="sales-plan",
            input_paths=[declared_actual_sales_path(case)],
            output_dir=output,
        )
        try:
            receipt = run_plan(case_path=case, output_dir=output)
        except ContractValidationError as exc:
            # A producer-declared contract refusal is correctable; runtime or
            # interrupted errors keep the native request unresolved instead.
            result = {"exit_status": 2, "contract_error": str(exc)}
        else:
            result = {"exit_status": 0 if receipt["status"] == "passed" else 1}
    elif request["operation"] == "run":
        status = run_cli(
            [
                "--case",
                request["case"],
                "--output-dir",
                request["output"],
                "--client-engagement",
                request["context"],
            ]
        )
        if status not in {0, 1}:
            raise ValueError("Sales Plan refused the selected contract")
        result = {"exit_status": status}
    else:
        raise ValueError("Unknown Sales Plan bridge operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
