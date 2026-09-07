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


@pytest.mark.parametrize("with_assessment", [True, False])
def test_blocked_thin_margin_case_withholds_stale_unbound_conclusions(
    with_assessment: bool,
) -> None:
    case = case_data()
    for row in case["financial"]["scenarios"][0]["schedule"]:
        row["operating_expenses"] = "385"
    if not with_assessment:
        case.pop("assessment")
    plan = build_plan(case, source_root=FIXTURE)

    rendered = compile_html(plan, source_root=FIXTURE)

    assert plan["status"] == "blocked"
    assert plan["accepted_narrative"] == []
    assert plan["case"]["narrative"] == case["narrative"]
    assert plan["calculations"]["base/2027-01/ebitda_margin"]["value"] == "0.015"
    assert "Business assessment withheld" in rendered
    visible_report = rendered.split('<script type="application/json"')[0]
    assert "Both modeled scenarios lose money" not in visible_report
    assert "Redesign the launch before committing further funds" not in visible_report
    assert "Authoritative calculation register" in rendered
    assert "Accepted observation disagrees" in rendered


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


def test_undated_commercial_economics_do_not_invent_forecast_month() -> None:
    case = commercial_case()
    case["financial"] = None
    case["periods"] = []
    case["observations"] = []
    case["resolutions"] = []
    case["assessment"]["charts"] = []
    case["commercial"][0]["period"] = None
    for assumption in case["assumptions"]:
        assumption["effective_periods"] = []
    case["presentation"] = {
        "language": "en",
        "tables": [],
        "actions": [],
        "source_notes": [],
    }
    case["narrative"].append(
        {
            "id": "undated-economics",
            "kind": "finding",
            "text": "Scoped operating result: {{result}}.",
            "claims": {
                "result": {
                    "calculation_id": "base/undated/commercial_operating_result",
                    "value": "-100",
                }
            },
            "basis_ids": ["cash-timing"],
            "rubric_id": None,
            "review": case["review"],
        }
    )
    case["assessment"]["sections"]["economics"] = ["undated-economics"]

    plan = build_plan(case, source_root=FIXTURE)

    assert plan["status"] == "partial"
    assert plan["case"]["periods"] == []
    assert (
        plan["calculations"]["base/undated/commercial_operating_result"]["value"]
        == "-100"
    )
    assert (
        plan["calculations"]["base/undated/commercial_operating_result"]["period"]
        is None
    )
    assert "Forecast horizon not yet established" in compile_html(
        plan, source_root=FIXTURE
    )
    assert "Undated operating period" in compile_html(plan, source_root=FIXTURE)


def test_undated_commercial_row_cannot_bypass_financial_period_scope() -> None:
    case = commercial_case()
    case["commercial"][0]["period"] = None

    with pytest.raises(PlanningError, match="Unknown commercial period"):
        build_plan(case, source_root=FIXTURE)


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


def test_idea_assessment_does_not_claim_financial_model_limitations():
    import json

    case = json.loads((FIXTURE / "idea-case.json").read_text())

    plan = build_plan(case, source_root=FIXTURE)

    assert plan["statements"] is None
    assert plan["limitations"] == case["limitations"] + [
        "Mechanical readiness is not an assessment of viability, market attractiveness or financeability."
    ]


def test_reported_earnings_label_preserves_exact_evidence_binding():
    from planning_report import build_charts

    case = case_data()
    plan = build_plan(case, source_root=FIXTURE)

    charts = build_charts(plan)

    chart = next(chart for chart in charts if chart["id"] == "reported-adjusted-base")
    series = chart["series"][0]
    assert series["label"] == "Reported EBITDA"
    assert (
        series["points"][0]["calculation_id"]
        == "base/2027-01/reported_ebitda_client-ebitda"
    )
    assert series["points"][0]["value"] == "200"


@pytest.mark.parametrize("owner", ["Clara", "Vera"])
@pytest.mark.parametrize("financial_required", [False, True])
def test_reviewed_idea_readiness_depends_on_requested_financials(
    owner, financial_required
):
    import json

    case = json.loads((FIXTURE / "idea-case.json").read_text())
    review = {
        "status": "reviewed",
        "reviewer": "Synthetic reviewer",
        "reviewed_at": "2026-09-06T12:00:00+02:00",
    }
    case["review"] = review.copy()
    for source in case["sources"]:
        source["review_status"] = "reviewed"
    for evidence in case["evidence"]:
        evidence.update(review)
    for narrative in case["narrative"]:
        narrative["review"] = review.copy()
    case["required_sections"] = ["business_analysis"] + (
        ["financial"] if financial_required else []
    )

    plan = build_plan(case, owner=owner, source_root=FIXTURE)

    assert plan["status"] == (
        "partial" if financial_required else "ready_for_professional_review"
    )
    assert (
        "Financial model unavailable; no capital recommendation is supported"
        in plan["unresolved_matters"]
    ) == financial_required


@pytest.mark.parametrize("financial_required,exit_code", [(False, 0), (True, 2)])
def test_reviewed_idea_cli_writes_expected_readiness(
    tmp_path, financial_required, exit_code
):
    import json
    import shutil
    import subprocess
    import sys

    from tests.plugins.test_business_planning import SCRIPT_ROOT, _clara_workspace

    case = json.loads((FIXTURE / "idea-case.json").read_text())
    review = {
        "status": "reviewed",
        "reviewer": "Synthetic reviewer",
        "reviewed_at": "2026-09-06T12:00:00+02:00",
    }
    case["review"] = review.copy()
    for source in case["sources"]:
        source["review_status"] = "reviewed"
    for evidence in case["evidence"]:
        evidence.update(review)
    for narrative in case["narrative"]:
        narrative["review"] = review.copy()
    case["required_sections"] = ["business_analysis"] + (
        ["financial"] if financial_required else []
    )
    workspace, case_path, output = _clara_workspace(tmp_path, case)
    shutil.copytree(FIXTURE / "sources", workspace / "sources")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "run_strategic_plan.py"),
            "--case",
            str(case_path),
            "--output-dir",
            str(output),
            "--case-workspace",
            str(workspace),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == exit_code, completed.stderr
    plan = json.loads((output / "business_plan.json").read_text())
    assert plan["status"] == (
        "partial" if financial_required else "ready_for_professional_review"
    )
