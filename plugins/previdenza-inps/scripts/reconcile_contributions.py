#!/usr/bin/env python3
"""Recalculate reviewer-approved contribution recipes with exact Decimal arithmetic."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    DivisionByZero,
    InvalidOperation,
)
from pathlib import Path
from typing import Any

from case_core import (
    ensure_safe_output_dir,
    mark_private_file,
    prepare_private_directory,
    write_json,
)

__all__ = ["evaluate_recipes", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = {"add", "divide", "multiply", "subtract"}
ROUNDING_MODES = {
    "ROUND_DOWN": ROUND_DOWN,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_UP": ROUND_UP,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _valid_approval_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _claim_map(claims: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, claim in enumerate(claims.get("claims", []), start=1):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or f"CL-{index:03d}")
        result[claim_id] = claim
    return result


def _fact_map(records: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(fact.get("fact_id")): fact
        for fact in records.get("facts", [])
        if isinstance(fact, dict) and fact.get("fact_id")
    }


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal-compatible value") from exc


def _calculate(operation: str, left: Decimal, right: Decimal) -> Decimal:
    if operation == "add":
        return left + right
    if operation == "subtract":
        return left - right
    if operation == "multiply":
        return left * right
    if operation == "divide":
        return left / right
    raise ValueError(f"unsupported operation: {operation}")


def _validate_operand(
    operand: dict[str, Any],
    *,
    fact_map: dict[str, dict[str, Any]],
    claim_map: dict[str, dict[str, Any]],
    recipe_id: str,
) -> Decimal:
    operand_id = str(operand.get("id", "")).strip()
    if not operand_id:
        raise ValueError(f"{recipe_id}: operand id is required")
    fact_refs = [str(value) for value in operand.get("source_fact_ids", [])]
    claim_refs = [str(value) for value in operand.get("source_claim_ids", [])]
    if not fact_refs and not claim_refs:
        raise ValueError(f"{recipe_id}.{operand_id}: provenance is required")
    unknown_facts = sorted(set(fact_refs) - set(fact_map))
    unknown_claims = sorted(set(claim_refs) - set(claim_map))
    if unknown_facts:
        raise ValueError(
            f"{recipe_id}.{operand_id}: unknown fact refs {', '.join(unknown_facts)}"
        )
    if unknown_claims:
        raise ValueError(
            f"{recipe_id}.{operand_id}: unknown claim refs {', '.join(unknown_claims)}"
        )
    for fact_id in fact_refs:
        if fact_map[fact_id].get("review_status") != "confirmed":
            raise ValueError(
                f"{recipe_id}.{operand_id}: fact {fact_id} is not confirmed"
            )
    for claim_id in claim_refs:
        claim = claim_map[claim_id]
        if claim.get("verdict") != "supported":
            raise ValueError(
                f"{recipe_id}.{operand_id}: claim {claim_id} is not fully supported"
            )
    value = _decimal(operand.get("value"), f"{recipe_id}.{operand_id}.value")
    if len(fact_refs) == 1:
        source_fact = fact_map[fact_refs[0]]
        if source_fact.get("value_type") in {"amount", "number", "percentage"}:
            fact_value = _decimal(
                source_fact.get("value"), f"{recipe_id}.{operand_id}.source_fact_value"
            )
            if fact_value != value:
                raise ValueError(
                    f"{recipe_id}.{operand_id}: explicit value differs from fact {fact_refs[0]}"
                )
    return value


def _evaluate_recipe(
    recipe: dict[str, Any],
    *,
    facts: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    recipe_id = str(recipe.get("recipe_id", "")).strip()
    if not recipe_id:
        return {
            "recipe_id": "",
            "status": "calculation_not_run",
            "errors": ["recipe_id is required"],
        }
    errors: list[str] = []
    if recipe.get("review_status") != "confirmed":
        errors.append("recipe review_status must be confirmed")
    approval = recipe.get("approval")
    if not isinstance(approval, dict):
        errors.append("professional recipe approval is required")
    else:
        if not str(approval.get("approved_by_id", "")).strip():
            errors.append("approval.approved_by_id is required")
        if approval.get("approved_by_role") != "professional_reviewer":
            errors.append("approval must come from a professional_reviewer")
        if not _valid_approval_datetime(approval.get("recorded_at")):
            errors.append("approval.recorded_at must include an ISO timezone")
        if not str(approval.get("basis", "")).strip():
            errors.append("approval.basis is required")
    basis_claim_id = str(recipe.get("formula_basis_claim_id", "")).strip()
    if not basis_claim_id:
        errors.append("formula_basis_claim_id is required")
    elif basis_claim_id not in claims:
        errors.append(f"unknown formula basis claim: {basis_claim_id}")
    elif claims[basis_claim_id].get("verdict") != "supported":
        errors.append(f"formula basis claim is not fully supported: {basis_claim_id}")
    elif claims[basis_claim_id].get("claim_type") != "calculation_basis":
        errors.append(
            f"formula basis claim must have claim_type calculation_basis: {basis_claim_id}"
        )

    rounding = recipe.get("rounding")
    if not isinstance(rounding, dict):
        errors.append("rounding object is required")
        rounding = {}
    places = rounding.get("places")
    mode_name = str(rounding.get("mode", ""))
    if not isinstance(places, int) or not 0 <= places <= 8:
        errors.append("rounding.places must be an integer from 0 to 8")
    if mode_name not in ROUNDING_MODES:
        errors.append(f"unsupported rounding mode: {mode_name or '<empty>'}")

    values: dict[str, Decimal] = {}
    operands = recipe.get("operands")
    if not isinstance(operands, list) or not operands:
        errors.append("at least one operand is required")
        operands = []
    for operand in operands:
        if not isinstance(operand, dict):
            errors.append("operand must be an object")
            continue
        operand_id = str(operand.get("id", "")).strip()
        if operand_id in values:
            errors.append(f"duplicate operand id: {operand_id}")
            continue
        try:
            values[operand_id] = _validate_operand(
                operand,
                fact_map=facts,
                claim_map=claims,
                recipe_id=recipe_id,
            )
        except ValueError as exc:
            errors.append(str(exc))

    step_results: list[dict[str, str]] = []
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("at least one calculation step is required")
        steps = []
    for step in steps:
        if not isinstance(step, dict):
            errors.append("calculation step must be an object")
            continue
        step_id = str(step.get("id", "")).strip()
        operation = str(step.get("operation", ""))
        inputs = step.get("inputs")
        if not step_id or step_id in values:
            errors.append(f"invalid or duplicate step id: {step_id or '<empty>'}")
            continue
        if operation not in OPERATIONS:
            errors.append(f"{step_id}: unsupported operation {operation or '<empty>'}")
            continue
        if not isinstance(inputs, list) or len(inputs) != 2:
            errors.append(f"{step_id}: exactly two inputs are required")
            continue
        left_id, right_id = map(str, inputs)
        if left_id not in values or right_id not in values:
            errors.append(
                f"{step_id}: input ids must refer to earlier operands or steps"
            )
            continue
        try:
            result = _calculate(operation, values[left_id], values[right_id])
        except (DivisionByZero, InvalidOperation, ZeroDivisionError):
            errors.append(f"{step_id}: invalid decimal operation")
            continue
        values[step_id] = result
        step_results.append(
            {
                "step_id": step_id,
                "operation": operation,
                "left": str(values[left_id]),
                "right": str(values[right_id]),
                "raw_result": str(result),
            }
        )

    if (
        errors
        or not step_results
        or not isinstance(places, int)
        or mode_name not in ROUNDING_MODES
    ):
        return {
            "recipe_id": recipe_id,
            "description": recipe.get("description", ""),
            "status": "calculation_not_run",
            "errors": errors or ["no valid calculation result"],
            "steps": step_results,
        }
    final_raw = values[step_results[-1]["step_id"]]
    quantum = Decimal(1).scaleb(-places)
    final_result = final_raw.quantize(quantum, rounding=ROUNDING_MODES[mode_name])
    return {
        "recipe_id": recipe_id,
        "description": recipe.get("description", ""),
        "period": recipe.get("period", {}),
        "formula_basis_claim_id": basis_claim_id,
        "status": "calculated",
        "steps": step_results,
        "raw_result": str(final_raw),
        "result": str(final_result),
        "unit": recipe.get("result_unit", "EUR"),
        "rounding": {"places": places, "mode": mode_name},
        "errors": [],
    }


def evaluate_recipes(
    recipes_payload: dict[str, Any],
    records_payload: dict[str, Any],
    claims_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate only explicitly confirmed arithmetic recipes.

    Determinism is justified here because the operations are exact arithmetic with
    an explicit formula, operands, provenance, and rounding contract. This function
    never chooses a contribution rate, legal regime, threshold, ceiling, or formula.
    """

    recipes = recipes_payload.get("recipes")
    if not isinstance(recipes, list):
        raise ValueError("recipes must be a list")
    facts = _fact_map(records_payload)
    claims = _claim_map(claims_payload)
    results = [
        _evaluate_recipe(recipe, facts=facts, claims=claims)
        for recipe in recipes
        if isinstance(recipe, dict)
    ]
    not_run = sum(result["status"] != "calculated" for result in results)
    return {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "evaluated_at": _utc_now(),
        "status": "passed" if results and not not_run else "calculation_not_run",
        "recipe_count": len(results),
        "calculated_count": len(results) - not_run,
        "not_run_count": not_run,
        "results": results,
        "semantic_scope": "not_performed",
    }


def _write_results_csv(path: Path, result: dict[str, Any]) -> None:
    fieldnames = [
        "recipe_id",
        "description",
        "status",
        "result",
        "unit",
        "formula_basis_claim_id",
        "errors",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in result["results"]:
            writer.writerow(
                {
                    "recipe_id": row.get("recipe_id", ""),
                    "description": row.get("description", ""),
                    "status": row.get("status", ""),
                    "result": row.get("result", ""),
                    "unit": row.get("unit", ""),
                    "formula_basis_claim_id": row.get("formula_basis_claim_id", ""),
                    "errors": "; ".join(row.get("errors", [])),
                }
            )
    mark_private_file(path)


def main(argv: list[str] | None = None) -> int:
    """Run reviewer-approved calculations and write audit artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipes", type=Path)
    parser.add_argument("case_records", type=Path)
    parser.add_argument("claims_review", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output_dir = ensure_safe_output_dir(args.output_dir, plugin_root=PLUGIN_ROOT)
        result = evaluate_recipes(
            _load_object(args.recipes),
            _load_object(args.case_records),
            _load_object(args.claims_review),
        )
        result["input_provenance"] = {
            "recipes": {
                "path": args.recipes.resolve().as_posix(),
                "sha256": _file_sha256(args.recipes),
            },
            "case_records": {
                "path": args.case_records.resolve().as_posix(),
                "sha256": _file_sha256(args.case_records),
            },
            "claims_review": {
                "path": args.claims_review.resolve().as_posix(),
                "sha256": _file_sha256(args.claims_review),
            },
        }
        prepare_private_directory(output_dir)
        results_path = write_json(output_dir / "calculation_results.json", result)
        csv_path = output_dir / "calculation_results.csv"
        _write_results_csv(csv_path, result)
        write_json(
            output_dir / "calculation_audit.json",
            {
                "schema_version": "1.0",
                "status": result["status"],
                "calculation_results_path": results_path.resolve().as_posix(),
                "calculation_results_sha256": _file_sha256(results_path),
                "calculation_results_csv_path": csv_path.resolve().as_posix(),
                "calculation_results_csv_sha256": _file_sha256(csv_path),
                "input_provenance": result["input_provenance"],
                "recipe_count": result["recipe_count"],
                "calculated_count": result["calculated_count"],
                "not_run_count": result["not_run_count"],
                "issues": [
                    {"recipe_id": row["recipe_id"], "errors": row["errors"]}
                    for row in result["results"]
                    if row["errors"]
                ],
            },
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        PermissionError,
        ValueError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 1
    if result["status"] != "passed":
        LOGGER.error("One or more calculations were not run.")
        return 1
    LOGGER.info("Calculated %s approved recipe(s).", result["calculated_count"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
