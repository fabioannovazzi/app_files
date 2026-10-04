"""Execute reviewed arithmetic and exact annual field mappings.

Fixed code is justified by reproducible Decimal arithmetic, units and references.
The host model and reviewer select the applicable formula, rates, capacity, loss
and deadline treatment. This module contains no tax rule or permanent field ID.
"""

from __future__ import annotations

from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from typing import Any

from .contracts import ContractError, indexed
from .engine import money

__all__ = ["coordinate_incentives", "reconcile_declarations"]


def _operation(
    operation: str, operands: list[tuple[Decimal, str]]
) -> tuple[Decimal, str]:
    values = [x[0] for x in operands]
    units = [x[1] for x in operands]
    if operation in ("SUM", "MIN", "MAX", "DIFFERENCE"):
        if len(set(units)) != 1:
            raise ContractError("Addition/comparison requires identical units")
        if operation == "SUM":
            return sum(values, Decimal(0)), units[0]
        if operation == "MIN":
            return min(values), units[0]
        if operation == "MAX":
            return max(values), units[0]
        if len(values) == 2:
            return values[0] - values[1], units[0]
    elif len(values) == 2:
        if operation == "PRODUCT":
            if units.count("EUR") > 1:
                raise ContractError("Multiplication cannot create squared currency")
            return values[0] * values[1], "EUR" if "EUR" in units else "RATIO"
        if operation == "QUOTIENT":
            if units == ["RATIO", "EUR"]:
                raise ContractError("Inverse currency is unsupported")
            return values[0] / values[1], "RATIO" if units[0] == units[1] else "EUR"
    raise ContractError("Unsupported operation or operand count")


def coordinate_incentives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate only the explicitly supplied, evidence-backed formula plans."""
    indexed(rows, "incentive_id")
    results = []
    for row in rows:
        references: dict[str, tuple[Decimal, str]] = {}
        trace = []
        if row["assessment"] != "RECALCULATION" and (
            row["inputs"] or row["steps"] or row["outputs"]
        ):
            raise ContractError(
                "An unresolved/no-overlap assessment cannot claim a calculation"
            )
        for item in row["inputs"]:
            if item["name"] in references:
                raise ContractError("Duplicate formula variable")
            if not item["evidence_ids"] and not item["source_ids"]:
                raise ContractError("Formula input needs evidence or source provenance")
            value = Decimal(item["value"])
            if not value.is_finite():
                raise ContractError("Formula inputs must be finite")
            references[item["name"]] = (value, item["unit"])
        with localcontext() as context:
            context.prec = 80
            for step in row["steps"]:
                if step["name"] in references:
                    raise ContractError("Formula step redefines a variable")
                if len(step["operands"]) < 2 or len(step["operands"]) > 20:
                    raise ContractError("Formula step needs two to twenty operands")
                if not set(step["operands"]) <= set(references):
                    raise ContractError("Unknown or forward formula reference")
                try:
                    result = _operation(
                        step["operation"], [references[key] for key in step["operands"]]
                    )
                except (DivisionByZero, InvalidOperation) as error:
                    raise ContractError("Invalid incentive arithmetic") from error
                if not result[0].is_finite() or abs(result[0]) > Decimal("1e30"):
                    raise ContractError("Formula result exceeds bounded arithmetic")
                references[step["name"]] = result
                trace.append({**step, "value": str(result[0]), "unit": result[1]})
            indexed(row["outputs"], "role")
            outputs = {}
            for item in row["outputs"]:
                if item["value_ref"] not in references:
                    raise ContractError("Unknown incentive output reference")
                value, unit = references[item["value_ref"]]
                outputs[item["role"]] = {
                    "value": money(value) if unit == "EUR" else str(value),
                    "unit": unit,
                }
        if row["assessment"] == "RECALCULATION" and not outputs:
            raise ContractError("Recalculation needs explicit outputs")
        if row["assessment"] != "UNRESOLVED" and (
            not row["evidence_ids"] or not row["source_ids"]
        ):
            raise ContractError(
                "Incentive conclusion needs evidence and applicable sources"
            )
        if row["due_date"] is not None and not row["deadline_source_ids"]:
            raise ContractError("A deadline requires a case-specific source")
        results.append(
            {
                "incentive_id": row["incentive_id"],
                "assessment": row["assessment"],
                "status": (
                    "PROPOSED" if row["assessment"] != "UNRESOLVED" else "BLOCKED"
                ),
                "allocation_ids": row["allocation_ids"],
                "period_id": row["period_id"],
                "regime": row["regime"],
                "conclusion": row["conclusion"],
                "trace": trace,
                "outputs": outputs,
                "action": row["action"],
                "due_date": row["due_date"],
                "deadline_source_ids": row["deadline_source_ids"],
                "deadline_reason": row["deadline_reason"],
            }
        )
    return results


def reconcile_declarations(
    mappings: list[dict[str, Any]],
    calculation: dict[str, Any],
    incentives: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare an annual reviewed mapping with exact calculated/report values."""
    incentive_index = indexed(incentives, "incentive_id")
    result = []
    seen: set[tuple[str, str, str, str]] = set()
    for model in mappings:
        if model["period_id"] != calculation["claim_period_id"]:
            raise ContractError("Return mapping must cover the claimed fiscal period")
        indexed(model["rows"], "mapping_id")
        roles = {r["role"] for r in model["rows"]}
        if not {"OPTION", "INCOME_DEDUCTION", "IRAP_DEDUCTION"} <= roles:
            raise ContractError(
                "Return bridge requires separate option, income and IRAP fields"
            )
        for row in model["rows"]:
            key = (
                model["period_id"],
                model["model_version"],
                row["form"],
                row["field"],
            )
            if key in seen:
                raise ContractError("Duplicate annual return field mapping")
            seen.add(key)
            role = row["role"]
            if role in ("INCOME_DEDUCTION", "IRAP_DEDUCTION"):
                if row["expected"] is not None or row["incentive_id"] is not None:
                    raise ContractError("Deduction fields must use the computed result")
                expected = calculation["additional_deduction"][
                    "income" if role == "INCOME_DEDUCTION" else "irap"
                ]
            elif role == "INCENTIVE_ADJUSTMENT":
                entry = incentive_index.get(row["incentive_id"])
                if entry is None or row["output_role"] not in entry["outputs"]:
                    raise ContractError(
                        "Return adjustment has no calculated incentive output"
                    )
                quantity = entry["outputs"][row["output_role"]]
                if quantity["unit"] != "EUR" or row["expected"] is not None:
                    raise ContractError("Adjustment requires a calculated EUR output")
                expected = quantity["value"]
            else:
                expected = row["expected"]
                if expected is None or not expected.strip():
                    raise ContractError(
                        "Option/notice needs an explicitly reviewed expected value"
                    )
            reported = row["reported"]
            if reported is not None and not row["reported_evidence_ids"]:
                raise ContractError("Reported return value requires selected evidence")
            difference = None
            if role in ("INCOME_DEDUCTION", "IRAP_DEDUCTION", "INCENTIVE_ADJUSTMENT"):
                if reported is not None:
                    try:
                        number = Decimal(reported)
                        if not number.is_finite() or number != number.quantize(
                            Decimal("0.01")
                        ):
                            raise ContractError(
                                "Reported return amount must be finite EUR cents"
                            )
                        difference = money(number - Decimal(expected))
                    except InvalidOperation as error:
                        raise ContractError(
                            "Reported return amount is not a decimal"
                        ) from error
                equal = difference == "0.00"
            else:
                equal = expected == reported
            result.append(
                {
                    **{k: v for k, v in model.items() if k != "rows"},
                    **row,
                    "expected": expected,
                    "difference": difference,
                    "status": (
                        "NOT_TESTED"
                        if reported is None
                        else "PASS" if equal else "FAIL"
                    ),
                }
            )
    return {
        "status": (
            "NOT_TESTED"
            if not result
            else "RECONCILED" if all(r["status"] == "PASS" for r in result) else "OPEN"
        ),
        "rows": result,
        "submitted": False,
    }
