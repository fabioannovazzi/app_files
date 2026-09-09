"""Check financing evidence coverage; never calculate a credit/investment verdict."""

from __future__ import annotations

from datetime import date
from typing import Any

from planning_cycle import narrative_groups
from planning_workflow import indexed, require

__all__ = ["FINANCING_SECTIONS", "review_financing"]

FINANCING_SECTIONS = {
    "bank_debt": {
        "business_credibility": "Business credibility and demand",
        "use_and_structure": "Use of funds and proposed loan terms",
        "repayment": "Repayment from operating cash",
        "downside": "Repayment under adverse conditions",
        "borrower": "Borrower, existing debt and sponsor contribution",
        "security": "Guarantees and collateral",
        "requirements": "Lender requirements and missing evidence",
    },
    "venture_equity": {
        "market": "Market opportunity and customer evidence",
        "advantage": "Competition and defensible advantage",
        "traction": "Traction and repeatable growth",
        "team": "Team and ability to execute",
        "milestones": "Use of funds and funded milestones",
        "runway": "Cash runway and further funding",
        "returns": "Ownership, dilution and investor return",
        "requirements": "Investor fit and missing evidence",
    },
}


def review_financing(
    case: dict[str, Any], narrative: list[dict[str, Any]], calculations: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate references and modeled horizon, not feasibility or approval."""
    financing = case.get("financing")
    if financing is None:
        return [], ["Financing purpose missing: internal planning or financing request"]
    require(set(financing) == {"purpose", "assessments"}, "Unexpected financing fields")
    require(
        financing["purpose"] in {"internal", "financing", "undecided"},
        "Unknown financing purpose",
    )
    assessments = indexed(financing["assessments"], "financing assessment")
    if financing["purpose"] != "financing":
        require(not assessments, "Select financing purpose before adding requests")
        return [], (
            ["Financing purpose remains undecided"]
            if financing["purpose"] == "undecided"
            else []
        )
    if not assessments:
        return [], ["Financing request has no assessment"]
    all_issues = []
    results = []
    available = {n["id"] for n in narrative}
    financial = case["financial"]
    scenarios = set(indexed(financial["scenarios"], "scenario")) if financial else set()
    for assessment in assessments.values():
        require(
            set(assessment)
            == {
                "id",
                "instrument",
                "provider",
                "request_ids",
                "conclusion",
                "rationale_ids",
                "sections",
                "scenario_ids",
                "coverage_end_period",
            },
            "Unexpected financing assessment fields",
        )
        instrument = assessment["instrument"]
        require(instrument in FINANCING_SECTIONS, "Unsupported financing instrument")
        require(
            assessment["provider"] is None
            or (
                isinstance(assessment["provider"], str)
                and assessment["provider"].strip()
            ),
            "Invalid financing provider",
        )
        require(
            assessment["conclusion"]
            in {"explore", "prepare_request", "revise_request", "not_suitable"},
            "Unknown financing conclusion",
        )
        require(
            set(assessment["sections"]) == set(FINANCING_SECTIONS[instrument]),
            "Financing assessment must cover its instrument's questions",
        )
        issues = narrative_groups(
            {
                "request": assessment["request_ids"],
                "rationale": assessment["rationale_ids"],
                **assessment["sections"],
            },
            case,
            available,
            f"Financing {assessment['id']}",
        )
        conclusion_available = not issues
        selected = assessment["scenario_ids"]
        require(
            isinstance(selected, list)
            and all(isinstance(s, str) for s in selected)
            and len(selected) == len(set(selected))
            and set(selected) <= scenarios,
            "Unknown or duplicate financing scenario",
        )
        end = assessment["coverage_end_period"]
        if end is not None:
            require(isinstance(end, str) and len(end) == 7, "Invalid financing horizon")
            date.fromisoformat(end + "-01")
        # A request cannot imply full repayment/milestone coverage from a shorter
        # forecast. No ratio threshold or prediction of lender approval is used.
        coverage = bool(end in case["periods"] and selected)
        metrics = ("ending_cash", "funding_requirement", "residual_funding_gap")
        if instrument == "bank_debt":
            metrics += ("debt_service", "cfads", "dscr")
        bindings = []
        for scenario in selected:
            for period in case["periods"]:
                if end is not None and period > end:
                    break
                for metric in metrics:
                    identifier = f"{scenario}/{period}/{metric}"
                    row = calculations.get(identifier)
                    if row is None or (row["value"] is None and metric != "dscr"):
                        coverage = False
                    elif row is not None:
                        bindings.append(identifier)
        if not coverage:
            issues.append(
                f"Financing {assessment['id']}: cash/repayment horizon incomplete"
            )
        if assessment["provider"] is None:
            issues.append(
                f"Financing {assessment['id']}: provider requirements unverified"
            )
        results.append(
            {
                "id": assessment["id"],
                "calculation_ids": bindings,
                "coverage_complete": coverage,
                "conclusion_available": conclusion_available,
                "request_ready": not issues,
                "unresolved_matters": issues,
            }
        )
        all_issues.extend(issues)
    return results, all_issues
