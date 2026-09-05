"""Structural checks for model-authored business judgment; no viability rules."""

from __future__ import annotations

from typing import Any

from planning_workflow import require

__all__ = ["SECTIONS", "review_assessment", "select_charts"]

SECTIONS = {
    "business": "The business and its customers",
    "market": "Demand and route to market",
    "operations": "How the business would operate",
    "economics": "Prices, costs and sustainable sales",
    "cash": "Cash, investment and financing",
    "alternatives": "Alternatives worth considering",
    "next_actions": "What to do next",
}


def review_assessment(
    case: dict[str, Any], narrative: list[dict[str, Any]]
) -> list[str]:
    """Require decision coverage, not an algorithmic verdict about its quality."""
    assessment = case.get("assessment")
    if assessment is None:
        return [
            "Business assessment missing: a financial workpaper is not a business plan"
        ]
    require(
        set(assessment)
        == {
            "decision",
            "recommendation",
            "depends_on",
            "would_change",
            "sections",
            "charts",
        },
        "Unexpected assessment fields",
    )
    require(
        assessment["decision"] in {"proceed", "test", "redesign", "stop"},
        "Unknown business recommendation",
    )
    require(
        set(assessment["sections"]) == set(SECTIONS),
        "Assessment must address every business question",
    )
    all_ids = {n["id"] for n in case["narrative"]}
    available = {n["id"] for n in narrative}
    groups = {
        key: assessment[key] for key in ("recommendation", "depends_on", "would_change")
    }
    groups.update(assessment["sections"])
    issues = []
    for label, ids in groups.items():
        require(
            isinstance(ids, list) and len(ids) == len(set(ids)),
            f"Invalid assessment references: {label}",
        )
        require(set(ids) <= all_ids, f"Unknown assessment narrative ID: {label}")
        if not ids or not set(ids) <= available:
            issues.append(
                f"Assessment {label} is incomplete or contains a withheld claim"
            )
    require(isinstance(assessment["charts"], list), "Chart selections must be a list")
    seen = set()
    for selection in assessment["charts"]:
        require(
            set(selection) == {"chart_id", "section", "caption_id"},
            "Invalid chart selection",
        )
        require(selection["section"] in SECTIONS, "Unknown chart section")
        require(selection["chart_id"] not in seen, "Duplicate selected chart")
        seen.add(selection["chart_id"])
        require(selection["caption_id"] in all_ids, "Unknown chart interpretation")
    return issues


def select_charts(
    plan: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Select existing canonical charts by explicit model-authored purpose."""
    assessment = plan["case"].get("assessment")
    if assessment is None:
        return candidates
    available = {chart["id"]: chart for chart in candidates}
    narrative = {n["id"] for n in plan["accepted_narrative"]}
    selected = []
    for selection in assessment["charts"]:
        identifier = selection["chart_id"]
        if identifier not in available:
            plan["unresolved_matters"].append(
                f"Selected chart {identifier} unavailable from calculated data"
            )
            continue
        if selection["caption_id"] not in narrative:
            plan["unresolved_matters"].append(
                f"Selected chart {identifier} interpretation withheld"
            )
            continue
        selected.append({**available[identifier], **selection})
    return selected
