"""Mechanical validation and comparison for Business Planning handoffs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "HANDOFF_REVIEW_SCHEMA",
    "HANDOFF_SCHEMA",
    "BusinessPlanningHandoffError",
    "counterpart_handoff_status",
    "review_counterpart_handoff",
]

HANDOFF_SCHEMA = "mparanza.business_planning_handoff.v2"
HANDOFF_REVIEW_SCHEMA = "mparanza.business_planning_handoff_review.v1"
_READY_PLAN_STATUS = "ready_for_professional_review"
_PLAN_STATUSES = {_READY_PLAN_STATUS, "partial", "blocked"}
_PRODUCT_LENSES = {
    "Vera": "accounting_financial",
    "Clara": "strategic_commercial",
}
_COMMON_FIELDS = {
    "schema_version",
    "workflow_id",
    "case_id",
    "entity_name",
    "company_stage",
    "planning_objective",
    "audience",
    "from_product",
    "from_lens",
    "to_product",
    "to_lens",
    "status",
    "source_plan_status",
    "source_review_status",
    "assumptions",
    "limitations",
    "handoff_boundary",
}
_LENS_FIELDS = {
    "Vera": {
        "financial_scenario_summaries",
        "reconciliation",
    },
    "Clara": {
        "recommendation",
        "initiatives",
        "risks",
        "open_questions",
    },
}


class BusinessPlanningHandoffError(ValueError):
    """Raised when a counterpart handoff violates the mechanical contract."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BusinessPlanningHandoffError(f"{label} must be an object")
    return value


def _list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise BusinessPlanningHandoffError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise BusinessPlanningHandoffError(f"{label} must be non-empty trimmed text")
    return value


def counterpart_handoff_status(plan_status: object) -> str:
    """Map a source plan status to an explicit counterpart-use status."""

    if plan_status == _READY_PLAN_STATUS:
        return "ready_for_counterpart_review"
    if plan_status == "partial":
        return "partial_source_plan"
    return "blocked_source_plan"


def _validate_handoff(
    handoff: Mapping[str, Any],
    *,
    receiving_product: str,
) -> tuple[str, str]:
    if receiving_product not in _PRODUCT_LENSES:
        raise BusinessPlanningHandoffError(
            f"Unsupported receiving product: {receiving_product}"
        )
    source_product = "Clara" if receiving_product == "Vera" else "Vera"
    expected_fields = _COMMON_FIELDS | _LENS_FIELDS[source_product]
    if set(handoff) != expected_fields:
        raise BusinessPlanningHandoffError(
            "counterpart handoff fields do not match the contract; "
            f"missing={sorted(expected_fields - set(handoff))}, "
            f"extra={sorted(set(handoff) - expected_fields)}"
        )
    if handoff["schema_version"] != HANDOFF_SCHEMA:
        raise BusinessPlanningHandoffError(
            f"counterpart handoff schema_version must be {HANDOFF_SCHEMA}"
        )
    if handoff["workflow_id"] != "business-planning":
        raise BusinessPlanningHandoffError(
            "counterpart handoff workflow_id must be business-planning"
        )
    if handoff["from_product"] != source_product:
        raise BusinessPlanningHandoffError(
            f"counterpart handoff from_product must be {source_product}"
        )
    if handoff["to_product"] != receiving_product:
        raise BusinessPlanningHandoffError(
            f"counterpart handoff to_product must be {receiving_product}"
        )
    if handoff["from_lens"] != _PRODUCT_LENSES[source_product]:
        raise BusinessPlanningHandoffError(
            "counterpart handoff from_lens does not match its source product"
        )
    if handoff["to_lens"] != _PRODUCT_LENSES[receiving_product]:
        raise BusinessPlanningHandoffError(
            "counterpart handoff to_lens does not match its receiving product"
        )
    source_status = _text(
        handoff["source_plan_status"], label="counterpart source_plan_status"
    )
    if source_status not in _PLAN_STATUSES:
        raise BusinessPlanningHandoffError(
            "counterpart source_plan_status is unsupported"
        )
    expected_status = counterpart_handoff_status(source_status)
    if handoff["status"] != expected_status:
        raise BusinessPlanningHandoffError(
            "counterpart handoff status does not match source_plan_status"
        )
    source_review_status = _text(
        handoff["source_review_status"], label="counterpart source_review_status"
    )
    if source_review_status != "draft_pending_professional_review":
        raise BusinessPlanningHandoffError(
            "counterpart source_review_status must be draft_pending_professional_review"
        )
    for field in (
        "case_id",
        "entity_name",
        "company_stage",
        "planning_objective",
        "audience",
        "handoff_boundary",
    ):
        _text(handoff[field], label=f"counterpart handoff {field}")
    _list(handoff["limitations"], label="counterpart handoff limitations")
    return source_status, source_review_status


def _assumption_map(
    values: object,
    *,
    label: str,
    expected_fields: set[str] | None = None,
) -> dict[str, str]:
    assumptions: dict[str, str] = {}
    for index, raw_item in enumerate(_list(values, label=label)):
        item = _mapping(raw_item, label=f"{label}[{index}]")
        if expected_fields is not None and set(item) != expected_fields:
            raise BusinessPlanningHandoffError(
                f"{label}[{index}] fields do not match the contract"
            )
        assumption_id = _text(item.get("id"), label=f"{label}[{index}].id")
        description = _text(
            item.get("description"), label=f"{label}[{index}].description"
        )
        if assumption_id in assumptions:
            raise BusinessPlanningHandoffError(
                f"{label} contains duplicate assumption ID: {assumption_id}"
            )
        if item.get("status") != "confirmed":
            raise BusinessPlanningHandoffError(
                f"{label}[{index}].status must be confirmed"
            )
        assumptions[assumption_id] = description
    return assumptions


def review_counterpart_handoff(
    case: Mapping[str, Any],
    handoff: Mapping[str, Any],
    *,
    receiving_product: str,
) -> dict[str, Any]:
    """Compare exact shared identifiers without resolving semantic divergence."""

    source_status, source_review_status = _validate_handoff(
        handoff,
        receiving_product=receiving_product,
    )
    receiving_assumptions = _assumption_map(
        case.get("assumptions"), label="receiving case assumptions"
    )
    source_product = str(handoff["from_product"])
    source_assumption_fields = {
        "id",
        "category",
        "description",
        "rationale",
        "status",
    }
    if source_product == "Vera":
        source_assumption_fields.add("effective_periods")
    source_assumptions = _assumption_map(
        handoff["assumptions"],
        label="counterpart handoff assumptions",
        expected_fields=source_assumption_fields,
    )
    shared_ids = sorted(set(receiving_assumptions) & set(source_assumptions))
    divergences = [
        {
            "assumption_id": assumption_id,
            "counterpart_description": source_assumptions[assumption_id],
            "receiving_case_description": receiving_assumptions[assumption_id],
        }
        for assumption_id in shared_ids
        if source_assumptions[assumption_id] != receiving_assumptions[assumption_id]
    ]
    identity_divergences = []
    for field in ("case_id", "entity_name"):
        if handoff[field] != case.get(field):
            identity_divergences.append(
                {
                    "field": field,
                    "counterpart_value": handoff[field],
                    "receiving_case_value": case.get(field),
                }
            )

    if source_status != _READY_PLAN_STATUS:
        status = "source_not_ready"
    elif identity_divergences or divergences:
        status = "divergence_requires_professional_review"
    elif not shared_ids:
        status = "no_shared_assumptions_requires_professional_review"
    else:
        status = "aligned_for_counterpart_use"

    return {
        "schema_version": HANDOFF_REVIEW_SCHEMA,
        "workflow_id": "business-planning",
        "case_id": case.get("case_id"),
        "receiving_product": receiving_product,
        "receiving_lens": _PRODUCT_LENSES[receiving_product],
        "counterpart_product": handoff["from_product"],
        "counterpart_lens": handoff["from_lens"],
        "source_plan_status": source_status,
        "source_review_status": source_review_status,
        "status": status,
        "identity_divergences": identity_divergences,
        "assumption_comparison": {
            "shared_assumption_ids": shared_ids,
            "aligned_assumption_ids": sorted(
                set(shared_ids) - {item["assumption_id"] for item in divergences}
            ),
            "description_divergences": divergences,
            "counterpart_only_assumption_ids": sorted(
                set(source_assumptions) - set(receiving_assumptions)
            ),
            "receiving_only_assumption_ids": sorted(
                set(receiving_assumptions) - set(source_assumptions)
            ),
        },
        "resolution_boundary": (
            "Exact IDs and descriptions are compared mechanically. Any identity, "
            "description, source-readiness, or missing-shared-assumption issue must "
            "be resolved by the professional; fixed code does not merge meanings."
        ),
    }
