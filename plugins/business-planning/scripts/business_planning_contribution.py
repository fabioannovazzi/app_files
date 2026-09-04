"""Mechanical contracts for optional Business Planning counterpart contributions.

The entry product remains the owner of the user request and final plan. This
module validates a bounded contribution from the other product, records exact
differences, and binds compatible content into the owner's result. Fixed code
does not decide whether two descriptions mean the same thing or whether a
strategic or financial conclusion is professionally sound.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

__all__ = [
    "CONTRIBUTION_REVIEW_SCHEMA",
    "CONTRIBUTION_SCHEMA",
    "BusinessPlanningContributionError",
    "attach_counterpart_contribution",
    "build_assumption_register",
    "counterpart_contribution_status",
    "review_counterpart_contribution",
    "write_assumption_register",
]

CONTRIBUTION_SCHEMA = "mparanza.business_planning_contribution.v1"
CONTRIBUTION_REVIEW_SCHEMA = "mparanza.business_planning_contribution_review.v1"
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
    "contribution_boundary",
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


class BusinessPlanningContributionError(ValueError):
    """Raised when a counterpart contribution violates its mechanical contract."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BusinessPlanningContributionError(f"{label} must be an object")
    return value


def _list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise BusinessPlanningContributionError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise BusinessPlanningContributionError(
            f"{label} must be non-empty trimmed text"
        )
    return value


def counterpart_contribution_status(plan_status: object) -> str:
    """Map source readiness to an explicit owner-review contribution status."""

    if plan_status == _READY_PLAN_STATUS:
        return "ready_for_owner_review"
    if plan_status == "partial":
        return "partial_contribution"
    return "blocked_contribution"


def _validate_contribution(
    contribution: Mapping[str, Any],
    *,
    receiving_product: str,
) -> tuple[str, str]:
    if receiving_product not in _PRODUCT_LENSES:
        raise BusinessPlanningContributionError(
            f"Unsupported receiving product: {receiving_product}"
        )
    source_product = "Clara" if receiving_product == "Vera" else "Vera"
    expected_fields = _COMMON_FIELDS | _LENS_FIELDS[source_product]
    if set(contribution) != expected_fields:
        raise BusinessPlanningContributionError(
            "counterpart contribution fields do not match the contract; "
            f"missing={sorted(expected_fields - set(contribution))}, "
            f"extra={sorted(set(contribution) - expected_fields)}"
        )
    if contribution["schema_version"] != CONTRIBUTION_SCHEMA:
        raise BusinessPlanningContributionError(
            "counterpart contribution schema_version must be " f"{CONTRIBUTION_SCHEMA}"
        )
    if contribution["workflow_id"] != "business-planning":
        raise BusinessPlanningContributionError(
            "counterpart contribution workflow_id must be business-planning"
        )
    if contribution["from_product"] != source_product:
        raise BusinessPlanningContributionError(
            f"counterpart contribution from_product must be {source_product}"
        )
    if contribution["to_product"] != receiving_product:
        raise BusinessPlanningContributionError(
            f"counterpart contribution to_product must be {receiving_product}"
        )
    if contribution["from_lens"] != _PRODUCT_LENSES[source_product]:
        raise BusinessPlanningContributionError(
            "counterpart contribution from_lens does not match its source product"
        )
    if contribution["to_lens"] != _PRODUCT_LENSES[receiving_product]:
        raise BusinessPlanningContributionError(
            "counterpart contribution to_lens does not match its receiving product"
        )
    source_status = _text(
        contribution["source_plan_status"],
        label="counterpart contribution source_plan_status",
    )
    if source_status not in _PLAN_STATUSES:
        raise BusinessPlanningContributionError(
            "counterpart contribution source_plan_status is unsupported"
        )
    if contribution["status"] != counterpart_contribution_status(source_status):
        raise BusinessPlanningContributionError(
            "counterpart contribution status does not match source_plan_status"
        )
    source_review_status = _text(
        contribution["source_review_status"],
        label="counterpart contribution source_review_status",
    )
    if source_review_status != "draft_pending_professional_review":
        raise BusinessPlanningContributionError(
            "counterpart contribution source_review_status must be "
            "draft_pending_professional_review"
        )
    for field in (
        "case_id",
        "entity_name",
        "company_stage",
        "planning_objective",
        "audience",
        "contribution_boundary",
    ):
        _text(
            contribution[field],
            label=f"counterpart contribution {field}",
        )
    _list(
        contribution["limitations"],
        label="counterpart contribution limitations",
    )
    return source_status, source_review_status


def _assumption_map(
    values: object,
    *,
    label: str,
    expected_fields: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    assumptions: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(_list(values, label=label)):
        item = dict(_mapping(raw_item, label=f"{label}[{index}]"))
        if expected_fields is not None and set(item) != expected_fields:
            raise BusinessPlanningContributionError(
                f"{label}[{index}] fields do not match the contract"
            )
        assumption_id = _text(item.get("id"), label=f"{label}[{index}].id")
        _text(item.get("description"), label=f"{label}[{index}].description")
        if assumption_id in assumptions:
            raise BusinessPlanningContributionError(
                f"{label} contains duplicate assumption ID: {assumption_id}"
            )
        if item.get("status") != "confirmed":
            raise BusinessPlanningContributionError(
                f"{label}[{index}].status must be confirmed"
            )
        assumptions[assumption_id] = item
    return assumptions


def review_counterpart_contribution(
    case: Mapping[str, Any],
    contribution: Mapping[str, Any],
    *,
    receiving_product: str,
) -> dict[str, Any]:
    """Record mechanically observable compatibility without semantic claims."""

    source_status, source_review_status = _validate_contribution(
        contribution,
        receiving_product=receiving_product,
    )
    receiving_assumptions = _assumption_map(
        case.get("assumptions"), label="receiving case assumptions"
    )
    source_product = str(contribution["from_product"])
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
        contribution["assumptions"],
        label="counterpart contribution assumptions",
        expected_fields=source_assumption_fields,
    )
    shared_ids = sorted(set(receiving_assumptions) & set(source_assumptions))
    description_differences = [
        {
            "assumption_id": assumption_id,
            "counterpart_description": source_assumptions[assumption_id]["description"],
            "receiving_case_description": receiving_assumptions[assumption_id][
                "description"
            ],
        }
        for assumption_id in shared_ids
        if source_assumptions[assumption_id]["description"]
        != receiving_assumptions[assumption_id]["description"]
    ]
    identity_differences = []
    for field in ("case_id", "entity_name"):
        if contribution[field] != case.get(field):
            identity_differences.append(
                {
                    "field": field,
                    "counterpart_value": contribution[field],
                    "receiving_case_value": case.get(field),
                }
            )
    context_differences = []
    for field in ("company_stage", "planning_objective", "audience"):
        if contribution[field] != case.get(field):
            context_differences.append(
                {
                    "field": field,
                    "counterpart_value": contribution[field],
                    "receiving_case_value": case.get(field),
                }
            )

    if source_status != _READY_PLAN_STATUS:
        status = "source_not_ready"
    elif identity_differences:
        status = "different_case"
    elif context_differences or description_differences or not shared_ids:
        status = "requires_owner_resolution"
    else:
        status = "mechanically_compatible"

    return {
        "schema_version": CONTRIBUTION_REVIEW_SCHEMA,
        "workflow_id": "business-planning",
        "case_id": case.get("case_id"),
        "receiving_product": receiving_product,
        "receiving_lens": _PRODUCT_LENSES[receiving_product],
        "counterpart_product": contribution["from_product"],
        "counterpart_lens": contribution["from_lens"],
        "source_plan_status": source_status,
        "source_review_status": source_review_status,
        "status": status,
        "identity_differences": identity_differences,
        "context_differences": context_differences,
        "assumption_comparison": {
            "shared_assumption_ids": shared_ids,
            "matching_description_ids": sorted(
                set(shared_ids)
                - {item["assumption_id"] for item in description_differences}
            ),
            "description_differences": description_differences,
            "counterpart_only_assumption_ids": sorted(
                set(source_assumptions) - set(receiving_assumptions)
            ),
            "receiving_only_assumption_ids": sorted(
                set(receiving_assumptions) - set(source_assumptions)
            ),
        },
        "compatibility_boundary": (
            "Fixed code checks source readiness, exact case identifiers, exact "
            "shared context text, and exact shared assumption IDs and descriptions. "
            "Mechanical compatibility does not establish semantic agreement, "
            "numerical consistency, feasibility, or professional approval."
        ),
    }


def build_assumption_register(
    owner_assumptions: object,
    *,
    owner_product: str,
    counterpart_assumptions: object | None = None,
    counterpart_product: str | None = None,
) -> list[dict[str, Any]]:
    """Create one provenance-preserving register without merging meanings."""

    if owner_product not in _PRODUCT_LENSES:
        raise BusinessPlanningContributionError(
            f"Unsupported owner product: {owner_product}"
        )
    owner = _assumption_map(owner_assumptions, label="owner assumptions")
    counterpart = (
        _assumption_map(counterpart_assumptions, label="counterpart assumptions")
        if counterpart_assumptions is not None
        else {}
    )
    if counterpart and counterpart_product not in _PRODUCT_LENSES:
        raise BusinessPlanningContributionError(
            "counterpart_product is required for counterpart assumptions"
        )

    register: list[dict[str, Any]] = []
    for assumption_id in sorted(set(owner) | set(counterpart)):
        owner_item = owner.get(assumption_id, {})
        counterpart_item = counterpart.get(assumption_id, {})
        if owner_item and counterpart_item:
            relationship = (
                "matching_description"
                if owner_item["description"] == counterpart_item["description"]
                else "description_difference"
            )
        elif owner_item:
            relationship = "owner_only"
        else:
            relationship = "counterpart_only"
        register.append(
            {
                "id": assumption_id,
                "relationship": relationship,
                "owner_product": owner_product,
                "owner_category": owner_item.get("category", ""),
                "owner_description": owner_item.get("description", ""),
                "owner_rationale": owner_item.get("rationale", ""),
                "owner_status": owner_item.get("status", ""),
                "owner_effective_periods": list(
                    owner_item.get("effective_periods", [])
                ),
                "counterpart_product": counterpart_product or "",
                "counterpart_category": counterpart_item.get("category", ""),
                "counterpart_description": counterpart_item.get("description", ""),
                "counterpart_rationale": counterpart_item.get("rationale", ""),
                "counterpart_status": counterpart_item.get("status", ""),
                "counterpart_effective_periods": list(
                    counterpart_item.get("effective_periods", [])
                ),
            }
        )
    return register


def _review_issues(review: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if review["status"] == "source_not_ready":
        issues.append(
            {
                "kind": "counterpart_source_not_ready",
                "detail": f"Source plan status: {review['source_plan_status']}",
            }
        )
    for item in review["identity_differences"]:
        issues.append({"kind": "case_identity_difference", **item})
    for item in review["context_differences"]:
        issues.append({"kind": "planning_context_difference", **item})
    for item in review["assumption_comparison"]["description_differences"]:
        issues.append({"kind": "assumption_description_difference", **item})
    if not review["assumption_comparison"]["shared_assumption_ids"]:
        issues.append(
            {
                "kind": "no_shared_assumptions",
                "detail": "The two cases have no shared assumption IDs.",
            }
        )
    return issues


def attach_counterpart_contribution(
    plan: Mapping[str, Any],
    contribution: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a checked contribution to the owner's final review package."""

    owner_product = _text(plan.get("owner_product"), label="plan.owner_product")
    if review.get("receiving_product") != owner_product:
        raise BusinessPlanningContributionError(
            "contribution review receiving_product does not match the plan owner"
        )
    source_product = _text(
        contribution.get("from_product"), label="contribution.from_product"
    )
    included = review.get("status") == "mechanically_compatible"
    issues = _review_issues(review)
    result = deepcopy(dict(plan))
    result["counterpart_contribution"] = {
        "source_product": source_product,
        "source_lens": contribution["from_lens"],
        "status": (
            "included_for_owner_review" if included else "requires_owner_resolution"
        ),
        "included_in_owner_plan": included,
        "source_plan_status": contribution["source_plan_status"],
        "source_review_status": contribution["source_review_status"],
        "shared_assumption_ids": review["assumption_comparison"][
            "shared_assumption_ids"
        ],
        "unresolved_issues": issues,
        "content": {
            field: deepcopy(contribution[field])
            for field in sorted(_LENS_FIELDS[source_product])
        },
        "review_boundary": review["compatibility_boundary"],
    }
    result["assumption_register"] = build_assumption_register(
        result["assumptions"],
        owner_product=owner_product,
        counterpart_assumptions=contribution["assumptions"],
        counterpart_product=source_product,
    )
    result["unresolved_issues"] = [
        *result.get("unresolved_issues", []),
        *issues,
    ]
    if not included and result["status"] != "blocked":
        result["status"] = "partial"
    return result


def write_assumption_register(path: Path, register: object) -> None:
    """Write the combined owner/counterpart assumption register as CSV."""

    rows = [
        dict(_mapping(item, label="assumption register row"))
        for item in _list(register, label="assumption register")
    ]
    fieldnames = (
        "id",
        "relationship",
        "owner_product",
        "owner_category",
        "owner_description",
        "owner_rationale",
        "owner_status",
        "owner_effective_periods",
        "counterpart_product",
        "counterpart_category",
        "counterpart_description",
        "counterpart_rationale",
        "counterpart_status",
        "counterpart_effective_periods",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "owner_effective_periods": "|".join(row["owner_effective_periods"]),
                    "counterpart_effective_periods": "|".join(
                        row["counterpart_effective_periods"]
                    ),
                }
            )
