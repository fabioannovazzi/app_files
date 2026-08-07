"""Recompute the small, versioned deterministic rule families allowed here."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

__all__ = ["RuleContractError", "validate_deterministic_rule"]


class RuleContractError(ValueError):
    """Raised when a claimed deterministic result is not reproducible."""


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuleContractError(f"{field} must be a finite decimal string") from exc
    if not number.is_finite():
        raise RuleContractError(f"{field} must be a finite decimal string")
    return number


def _date(value: object, *, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise RuleContractError(f"{field} must use YYYY-MM-DD") from exc


def _compare(left: Any, operator: object, right: Any) -> bool:
    operations: dict[str, Callable[[Any, Any], bool]] = {
        "<": lambda first, second: first < second,
        "<=": lambda first, second: first <= second,
        "==": lambda first, second: first == second,
        ">=": lambda first, second: first >= second,
        ">": lambda first, second: first > second,
    }
    operation = operations.get(str(operator))
    if operation is None:
        raise RuleContractError("operator must be one of <, <=, ==, >=, >")
    return operation(left, right)


def _evaluate(rule_id: str, inputs: dict[str, Any]) -> bool:
    """Evaluate only fixed-format comparisons whose correctness is mechanical."""

    if set(inputs) != {"left", "operator", "right"}:
        raise RuleContractError("inputs must contain exactly left, operator, and right")
    if rule_id == "exact_decimal_compare":
        return _compare(
            _decimal(inputs["left"], field="inputs.left"),
            inputs["operator"],
            _decimal(inputs["right"], field="inputs.right"),
        )
    if rule_id == "exact_date_compare":
        return _compare(
            _date(inputs["left"], field="inputs.left"),
            inputs["operator"],
            _date(inputs["right"], field="inputs.right"),
        )
    raise RuleContractError(f"unsupported deterministic rule: {rule_id}")


def validate_deterministic_rule(
    rule: object,
    *,
    assessment_outcome: object,
) -> None:
    """Verify exact result and professionally supplied result-to-outcome mapping."""

    if not isinstance(rule, dict):
        raise RuleContractError("deterministic_rule must be an object")
    required = {
        "rule_id",
        "version",
        "reason",
        "inputs",
        "result",
        "outcome_map",
    }
    if set(rule) != required:
        raise RuleContractError(
            "deterministic_rule must contain exactly rule_id, version, reason, "
            "inputs, result, and outcome_map"
        )
    if rule["version"] != "1":
        raise RuleContractError("deterministic rule version must be 1")
    if not str(rule["reason"]).strip():
        raise RuleContractError("deterministic rule reason is required")
    inputs = rule["inputs"]
    if not isinstance(inputs, dict):
        raise RuleContractError("deterministic rule inputs must be an object")
    calculated = _evaluate(str(rule["rule_id"]), inputs)
    if not isinstance(rule["result"], bool) or rule["result"] is not calculated:
        raise RuleContractError("recorded deterministic result does not reproduce")
    outcome_map = rule["outcome_map"]
    if not isinstance(outcome_map, dict) or set(outcome_map) != {"true", "false"}:
        raise RuleContractError("outcome_map must contain exactly true and false")
    expected_outcome = outcome_map["true" if calculated else "false"]
    if assessment_outcome != expected_outcome:
        raise RuleContractError(
            "assessment outcome contradicts the reproduced deterministic result"
        )
