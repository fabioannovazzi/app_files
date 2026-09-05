"""Decision-led report regressions, without pretending to score semantic quality."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tests.plugins.test_business_planning_shared import (
    FIXTURE,
    PlanningError,
    bind_plugin_imports,
    build_plan,
    case_data,
    compile_html,
)


def test_financial_workpaper_alone_cannot_be_a_ready_business_plan() -> None:
    case = case_data()
    case.pop("assessment")
    plan = build_plan(case, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "Business assessment incomplete" in compile_html(plan, source_root=FIXTURE)


@pytest.mark.parametrize(
    "section",
    [
        "business",
        "market",
        "operations",
        "economics",
        "cash",
        "alternatives",
        "next_actions",
    ],
)
def test_unanswered_business_question_prevents_readiness(section: str) -> None:
    case = case_data()
    case["assessment"]["sections"][section] = []
    plan = build_plan(case, source_root=FIXTURE)
    assert (
        f"Assessment {section} is incomplete or contains a withheld claim"
        in plan["unresolved_matters"]
    )
    assert plan["status"] == "partial"


def test_recommendation_precedes_analysis_and_collapsed_workpapers() -> None:
    plan = build_plan(case_data(), source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert (
        rendered.index('id="recommendation"')
        < rendered.index('id="market"')
        < rendered.index('id="supporting-evidence"')
    )
    assert '<details id="supporting-evidence">' in rendered
    assert rendered.index('id="cash-base"') < rendered.index('id="supporting-evidence"')
    assert len(plan["charts"]) == 4
    assert 'id="sources-uses-base"' not in rendered


def test_pending_professional_review_keeps_reasoned_recommendation_visible() -> None:
    case = case_data()
    case["review"] = {"status": "pending"}
    case["narrative"][1]["review"] = {"status": "pending"}
    plan = build_plan(case, source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "Redesign the launch before committing further funds" in rendered
    assert "Provisional interpretation" in rendered


def test_unknown_chart_cannot_silently_disappear_from_ready_report() -> None:
    case = case_data()
    case["assessment"]["charts"][0]["chart_id"] = "unsupported-chart"
    plan = build_plan(case, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "Selected chart unsupported-chart unavailable" in " ".join(
        plan["unresolved_matters"]
    )


def test_source_fact_number_does_not_require_a_financial_calculation() -> None:
    case = case_data()
    case["evidence"][0].update(
        claim_type="external_fact", value="2027", unit="calendar year"
    )
    entry = case["narrative"][2]
    entry.update(
        text="The source describes a launch in {{year}}.",
        basis_ids=[case["evidence"][0]["id"]],
        claims={"year": {"evidence_id": case["evidence"][0]["id"], "value": "2027"}},
    )
    plan = build_plan(case, source_root=FIXTURE)
    assert plan["status"] == "ready_for_professional_review"
    assert "2027 calendar year" in compile_html(plan, source_root=FIXTURE)


def test_source_numeric_mismatch_blocks_readiness() -> None:
    case = case_data()
    case["evidence"][0].update(
        claim_type="external_fact", value="2027", unit="calendar year"
    )
    case["narrative"][2].update(
        text="Launch in {{year}}.",
        basis_ids=[case["evidence"][0]["id"]],
        claims={"year": {"evidence_id": case["evidence"][0]["id"], "value": "2028"}},
    )
    plan = build_plan(case, source_root=FIXTURE)
    assert plan["status"] == "blocked"


def commercial_case() -> dict:
    case = case_data()
    case["commercial"] = [
        dict(
            scenario="base",
            period="2027-01",
            units="100",
            net_price="10",
            variable_cost_per_unit="6",
            fixed_cost="500",
            basis_ids=["cash-timing"],
            cost_scope="Synthetic complete variable and fixed operating costs; excludes financing and taxes.",
        )
    ]
    return case


def test_commercial_drivers_reconcile_with_linked_financial_model() -> None:
    plan = build_plan(commercial_case(), source_root=FIXTURE)
    assert plan["status"] == "ready_for_professional_review"
    assert (
        plan["calculations"]["base/2027-01/commercial_operating_result"]["value"]
        == "-100"
    )
    assert (
        plan["calculations"]["base/2027-01/commercial_break_even_units"]["value"]
        == "125"
    )


def test_commercial_disagreement_blocks_both_outputs() -> None:
    case = commercial_case()
    case["commercial"][0]["units"] = "200"
    vera = build_plan(case, owner="Vera", source_root=FIXTURE)
    clara = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert vera == clara
    assert vera["status"] == "blocked"
    assert "Commercial revenue disagrees" in " ".join(vera["unresolved_matters"])


def test_unit_economics_remain_available_without_complete_cash_forecast() -> None:
    case = commercial_case()
    case["financial"] = None
    case["observations"] = []
    case["resolutions"] = []
    case["assessment"]["charts"] = []
    plan = build_plan(case, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert (
        plan["calculations"]["base/2027-01/commercial_contribution_per_unit"]["value"]
        == "4"
    )
    assert not any(
        c["metric"] == "funding_requirement" for c in plan["calculations"].values()
    )


def test_nonpositive_unit_contribution_has_no_finite_break_even() -> None:
    case = commercial_case()
    case["commercial"][0]["variable_cost_per_unit"] = "10"
    plan = build_plan(case, source_root=FIXTURE)
    assert (
        plan["calculations"]["base/2027-01/commercial_break_even_units"]["value"]
        is None
    )


def test_idea_can_be_assessed_without_fabricated_periods_or_currency() -> None:
    case = case_data()
    case.update(
        financial=None,
        periods=[],
        reporting_currency=None,
        observations=[],
        resolutions=[],
    )
    for assumption in case["assumptions"]:
        assumption["effective_periods"] = []
    case["assessment"]["charts"] = []
    case["narrative"][0].update(
        kind="limitation",
        text="Sustainable sales are unknown until prices and full costs are established.",
        claims={},
        basis_ids=[],
    )
    plan = build_plan(case, source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "Forecast horizon not yet established" in rendered
    assert "Currency not established" in rendered
    assert "Recommendation: Redesign" in rendered
    assert plan["calculations"] == {}


def test_unknown_assessment_reference_is_rejected() -> None:
    case = case_data()
    case["assessment"]["recommendation"] = ["missing-id"]
    with pytest.raises(PlanningError, match="Unknown assessment narrative ID"):
        build_plan(case, source_root=FIXTURE)


def test_registered_idea_fixture_remains_provisional_and_decision_useful() -> None:
    import json

    case = json.loads((FIXTURE / "idea-case.json").read_text())
    plan = build_plan(case, source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "Recommendation: Test" in rendered
    assert "Test the service before buying a vehicle" in rendered
    assert "paid bookings and actual job and travel time" in rendered
    assert not plan["calculations"] and not plan["charts"]
    assert plan == build_plan(case, source_root=FIXTURE, owner="Vera")
