"""Mechanical accounting-readiness controls for variance-analysis runs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = [
    "accounting_intake_questions",
    "default_accounting_review",
    "evaluate_accounting_readiness",
    "normalize_accounting_review",
]

DEFAULT_TOLERANCE = 0.01


def default_accounting_review() -> dict[str, Any]:
    """Return the explicit review fields required for an accounting handoff."""

    return {
        "perimeter": {"status": "pending", "description": None},
        "source_tie_out": {
            "baseline_source_total": None,
            "comparison_source_total": None,
            "tolerance": DEFAULT_TOLERANCE,
        },
        "favorable_adverse_convention": {
            "status": "pending",
            "description": None,
        },
        "materiality": {
            "status": "pending",
            "threshold": None,
            "basis": None,
        },
        "professional_review": {
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
        },
        "root_cause_review": {
            "status": "pending",
            "selected_alternative": None,
            "rationale": None,
        },
    }


def normalize_accounting_review(value: Any) -> dict[str, Any]:
    """Merge supplied review fields into the stable accounting-review shape."""

    normalized = default_accounting_review()
    if not isinstance(value, dict):
        return normalized
    for section, defaults in tuple(normalized.items()):
        supplied = value.get(section)
        if isinstance(supplied, dict):
            normalized[section] = {**defaults, **deepcopy(supplied)}
    return normalized


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def accounting_intake_questions(review: dict[str, Any]) -> list[str]:
    """Return mechanically unresolved accounting-review fields.

    Presence checks are deterministic because they enforce an auditable intake
    contract; the code does not decide the semantic content of any answer.
    """

    normalized = normalize_accounting_review(review)
    questions: list[str] = []
    perimeter = normalized["perimeter"]
    if perimeter.get("status") != "established" or not _text(
        perimeter.get("description")
    ):
        questions.append("Confirm the entity and consolidation perimeter.")

    tie_out = normalized["source_tie_out"]
    if (
        _number(tie_out.get("baseline_source_total")) is None
        or _number(tie_out.get("comparison_source_total")) is None
    ):
        questions.append(
            "Provide approved baseline and comparison source totals for tie-out."
        )

    convention = normalized["favorable_adverse_convention"]
    if convention.get("status") != "established" or not _text(
        convention.get("description")
    ):
        questions.append("Confirm the favorable/adverse sign convention.")

    materiality = normalized["materiality"]
    materiality_status = str(materiality.get("status") or "pending")
    if materiality_status == "applied":
        if _number(materiality.get("threshold")) is None or not _text(
            materiality.get("basis")
        ):
            questions.append("Complete the applied materiality threshold and basis.")
    elif materiality_status != "not_applied":
        questions.append(
            "Confirm materiality or explicitly record that it is not applied."
        )
    return questions


def evaluate_accounting_readiness(
    review: dict[str, Any],
    *,
    amount_baseline: float,
    amount_comparison: float,
    max_abs_component_reconciliation_delta: float | None,
) -> dict[str, Any]:
    """Evaluate only mechanically verifiable readiness and tie-out controls."""

    normalized = normalize_accounting_review(review)
    tie_out = normalized["source_tie_out"]
    tolerance = _number(tie_out.get("tolerance"))
    if tolerance is None or tolerance < 0:
        tolerance = DEFAULT_TOLERANCE
    baseline_source_total = _number(tie_out.get("baseline_source_total"))
    comparison_source_total = _number(tie_out.get("comparison_source_total"))
    baseline_delta = (
        amount_baseline - baseline_source_total
        if baseline_source_total is not None
        else None
    )
    comparison_delta = (
        amount_comparison - comparison_source_total
        if comparison_source_total is not None
        else None
    )
    if baseline_delta is None or comparison_delta is None:
        source_status = "not_established"
    elif abs(baseline_delta) <= tolerance and abs(comparison_delta) <= tolerance:
        source_status = "passed"
    else:
        source_status = "failed"

    if max_abs_component_reconciliation_delta is None:
        bridge_status = "not_established"
    elif abs(max_abs_component_reconciliation_delta) <= tolerance:
        bridge_status = "passed"
    else:
        bridge_status = "failed"

    unresolved = accounting_intake_questions(normalized)
    if source_status == "failed":
        unresolved.append("Resolve the failed source-total tie-out.")
    if bridge_status != "passed":
        unresolved.append("Resolve the component-bridge reconciliation control.")

    if source_status == "failed" or bridge_status == "failed":
        accounting_status = "blocked"
    elif unresolved or source_status != "passed" or bridge_status != "passed":
        accounting_status = "partial"
    else:
        accounting_status = "ready_for_professional_review"

    professional = normalized["professional_review"]
    root_cause = normalized["root_cause_review"]
    professional_approved = (
        professional.get("status") == "approved"
        and bool(_text(professional.get("reviewed_by")))
        and bool(_text(professional.get("reviewed_at")))
    )
    root_cause_approved = (
        root_cause.get("status") == "approved"
        and isinstance(root_cause.get("selected_alternative"), int)
        and bool(_text(root_cause.get("rationale")))
    )
    client_report_status = (
        "approved_for_client_use"
        if accounting_status == "ready_for_professional_review"
        and professional_approved
        and root_cause_approved
        else "draft_pending_professional_review"
    )
    return {
        "accounting_status": accounting_status,
        "client_report_status": client_report_status,
        "source_tie_out": {
            "status": source_status,
            "tolerance": tolerance,
            "baseline_source_total": baseline_source_total,
            "baseline_calculated_total": amount_baseline,
            "baseline_delta": baseline_delta,
            "comparison_source_total": comparison_source_total,
            "comparison_calculated_total": amount_comparison,
            "comparison_delta": comparison_delta,
        },
        "component_bridge": {
            "status": bridge_status,
            "max_abs_reconciliation_delta": max_abs_component_reconciliation_delta,
        },
        "perimeter": normalized["perimeter"],
        "favorable_adverse_convention": normalized["favorable_adverse_convention"],
        "materiality": normalized["materiality"],
        "professional_review": professional,
        "root_cause_review": root_cause,
        "unresolved_items": list(dict.fromkeys(unresolved)),
    }
