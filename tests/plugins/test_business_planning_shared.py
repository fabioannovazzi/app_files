"""Sanitized regression evaluation of the registered owner entry points."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for plugin_import_root in (
    REPO_ROOT / "plugins/business-planning/scripts",
    REPO_ROOT / "plugins/_shared/vendor/modules",
):
    sys.path.insert(0, str(plugin_import_root))

import planning_report as REPORT_MODULE
import planning_workflow as WORKFLOW_MODULE
from planning_report import compile_html, export_pdf, write_package
from planning_workflow import PlanningError, build_plan, validate_plan

from tests.plugins.test_business_planning import (
    SCRIPT_ROOT,
    _clara_workspace,
    _load_customer_ledger,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "business_planning"


@pytest.fixture(autouse=True)
def bind_plugin_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore isolated plugin imports after the repo's import-cleanup hook."""
    monkeypatch.syspath_prepend(str(SCRIPT_ROOT))
    monkeypatch.setitem(sys.modules, "planning_report", REPORT_MODULE)
    monkeypatch.setitem(sys.modules, "planning_workflow", WORKFLOW_MODULE)


def case_data() -> dict:
    return json.loads((FIXTURE / "case.json").read_text())


def test_both_entry_points_have_identical_plans_and_html() -> None:
    case = case_data()
    vera = build_plan(case, owner="Vera", source_root=FIXTURE)
    clara = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert vera["status"] == "ready_for_professional_review"
    assert vera == clara
    assert compile_html(vera, source_root=FIXTURE) == compile_html(
        clara, source_root=FIXTURE
    )
    assert vera["calculations"] == clara["calculations"]
    assert vera["calculations_sha256"] == clara["calculations_sha256"]
    assert vera["calculations"]["base/2027-01/ebitda"]["value"] == "-100"
    assert vera["calculations"]["base/2027-01/ebitda_margin"]["value"] == "-0.1"
    assert vera["calculations"]["base/2027-01/operating_cash_flow"]["value"] == "-110"
    assert vera["calculations"]["base/2027-02/ending_cash"]["value"] == "280"
    assert vera["calculations"]["base/2027-03/funding_requirement"]["value"] == "330"
    assert vera["calculations"]["base/2027-03/residual_funding_gap"]["value"] == "60"
    assert vera["calculations"]["base/2027-01/break_even_revenue"]["value"] == "1250"
    assert vera["calculations"]["base/2027-01/margin_of_safety"]["value"] == "-0.25"
    assert vera["calculations"]["base/2027-02/debt_service"]["value"] == "60"
    assert vera["calculations"]["base/2027-01/dscr"]["value"] == "-10"
    assert vera["calculations"]["base/2027-03/sources_uses_difference"]["value"] == "0"


def test_registered_skills_and_marketplace_cards_are_identical() -> None:
    vera_root = REPO_ROOT / "plugins/vera"
    clara_root = REPO_ROOT / "plugins/clara"
    skill = "skills/business-planning/SKILL.md"
    assert (vera_root / skill).read_text() == (clara_root / skill).read_text()
    vera_cards = json.loads(
        (vera_root / "marketplace_skill_instructions.json").read_text()
    )
    clara_cards = json.loads(
        (clara_root / "marketplace_skill_instructions.json").read_text()
    )
    assert (
        vera_cards["skills"]["business-planning"]
        == clara_cards["skills"]["business-planning"]
    )


@pytest.mark.parametrize("entry_point", ["Vera", "Clara"])
def test_missing_reviewed_business_analysis_is_partial_for_either_entry(
    entry_point: str,
) -> None:
    case = case_data()
    case["narrative"][0]["review"]["status"] = "unverified"
    plan = build_plan(case, owner=entry_point, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert (
        "Narrative profit-risk: requires professional review"
        in plan["unresolved_matters"]
    )


def test_product_labelled_v2_case_requires_explicit_migration() -> None:
    case = case_data()
    case["schema_version"] = "mparanza.business_planning_case.v2"
    with pytest.raises(PlanningError, match="shared v3 case"):
        build_plan(case, source_root=FIXTURE)


def test_accepted_negative_ebitda_cannot_revert_to_positive_model() -> None:
    case = case_data()
    case["financial"]["scenarios"][0]["schedule"][0]["operating_expenses"] = "200"
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert plan["status"] == "blocked"
    assert "Accepted observation disagrees" in " ".join(plan["unresolved_matters"])


def test_clara_stale_positive_ebitda_blocks_narrative_finalization() -> None:
    case = case_data()
    case["narrative"][0]["claims"]["ebitda"]["value"] = "200"
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert plan["status"] == "blocked"
    assert "profit-risk" not in {n["id"] for n in plan["accepted_narrative"]}
    assert "financial number disagrees" in " ".join(plan["unresolved_matters"])


def test_unresolved_source_conflict_stays_visible_and_partial() -> None:
    case = case_data()
    case["resolutions"] = []
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "Unresolved material conflict" in rendered
    assert "client-ebitda" in rendered and "adjusted-ebitda" in rendered


def test_missing_debt_repayment_is_not_zero_and_suppresses_capital_claim() -> None:
    case = case_data()
    case["financial"]["scenarios"][0]["schedule"][1]["debt_repayments"] = None
    entry = deepcopy(case["narrative"][0])
    entry.update(
        id="capital",
        kind="capital_recommendation",
        text="The cash model requires {{amount}}.",
        claims={
            "amount": {
                "calculation_id": "base/2027-03/funding_requirement",
                "value": "330",
            }
        },
    )
    case["narrative"].append(entry)
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert plan["status"] != "ready_for_professional_review"
    assert "base/2027-03/funding_requirement" not in plan["calculations"]
    assert "base/2027-02/debt_repayments" in " ".join(plan["unresolved_matters"])
    assert (
        plan["case"]["financial"]["scenarios"][0]["schedule"][1]["debt_repayments"]
        is None
    )
    assert not any(
        n["kind"] == "capital_recommendation" for n in plan["accepted_narrative"]
    )


@pytest.mark.parametrize("kind", ["score", "benchmark", "kpi"])
def test_unsupported_rubric_is_rejected(kind: str) -> None:
    case = case_data()
    case["narrative"][0]["kind"] = kind
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "reviewed rubric" in " ".join(plan["unresolved_matters"])
    assert "profit-risk" not in {n["id"] for n in plan["accepted_narrative"]}


def test_unconfirmed_material_assumption_prevents_final_readiness() -> None:
    case = case_data()
    case["assumptions"][0]["status"] = "proposed"
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "not confirmed" in " ".join(plan["unresolved_matters"])


def test_internal_material_cannot_be_republished_without_audience_decisions(
    tmp_path: Path,
) -> None:
    case = case_data()
    case["audience"] = "bank"
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    with pytest.raises(PlanningError, match="Audience restriction"):
        write_package(plan, source_root=FIXTURE, output=tmp_path / "report")
    assert not (tmp_path / "report").exists()


def test_exact_reviewed_audience_releases_allow_report() -> None:
    case = case_data()
    case["audience"] = "bank"
    for source in case["sources"]:
        case["decisions"].append(
            {
                "id": f"release-{source['id']}",
                "kind": "audience_release",
                "source_ids": [source["id"]],
                "source_sha256": source["sha256"],
                "audience": "bank",
                "rationale": "Synthetic release decision.",
                **case["review"],
            }
        )
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert "Audience: bank" in compile_html(plan, source_root=FIXTURE)


def test_source_hash_drift_is_rejected(tmp_path: Path) -> None:
    shutil.copytree(FIXTURE, tmp_path / "inputs")
    (tmp_path / "inputs/sources/client-model.txt").write_text("changed")
    with pytest.raises(PlanningError, match="hash mismatch"):
        build_plan(case_data(), owner="Vera", source_root=tmp_path / "inputs")


@pytest.mark.parametrize(
    "mutation", ["calculation", "chart", "statement", "hash", "lineage"]
)
def test_export_rejects_tampered_calculations_charts_and_receipts(
    mutation: str,
) -> None:
    plan = build_plan(case_data(), owner="Vera", source_root=FIXTURE)
    if mutation == "calculation":
        plan["calculations"]["base/2027-01/ebitda"]["value"] = "200"
    elif mutation == "chart":
        plan["charts"][0]["series"][0]["points"][0]["value"] = "999"
    elif mutation == "statement":
        plan["statements"]["scenarios"][0]["periods"][0]["cash_flow"][
            "ending_cash"
        ] = "999"
    elif mutation == "hash":
        plan["calculations_sha256"] = "changed"
    else:
        plan["calculations"]["base/2027-01/ebitda"]["source_ids"] = []
    with pytest.raises(PlanningError, match="canonical replay"):
        compile_html(plan, source_root=FIXTURE)


@pytest.mark.parametrize(
    "field", ["input_refs", "source_id", "duplicate_id", "periods"]
)
def test_invalid_lineage_and_identity_are_rejected(field: str) -> None:
    case = case_data()
    if field == "input_refs":
        case["financial"]["scenarios"][0]["schedule"][0]["input_refs"]["revenue"] = []
    elif field == "source_id":
        case["evidence"][0]["source_ids"] = ["unknown"]
    elif field == "duplicate_id":
        case["sources"].append(deepcopy(case["sources"][0]))
    else:
        case["periods"] = list(reversed(case["periods"]))
    with pytest.raises(PlanningError):
        build_plan(case, owner="Vera", source_root=FIXTURE)


def test_final_html_has_decision_charts_complete_provenance_and_safe_markup() -> None:
    case = case_data()
    case["entity_name"] = '<script>alert("x")</script>'
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert 'id="ebitda-scenarios"' in rendered
    assert 'id="reported-adjusted-base"' in rendered
    assert 'id="cash-base"' in rendered
    assert 'id="funding-base"' in rendered
    assert 'class="zero-line"' in rendered
    assert 'data-calculation-id="base/2027-01/ebitda"' in rendered
    assert "<script>alert" not in rendered
    assert all(s["sha256"] in rendered for s in case["sources"])
    assert "cash-timing" in rendered and "accept-adjustment" in rendered
    assert "debt_repayments" in rendered


def test_output_csv_json_html_and_receipt_share_calculation_register(
    tmp_path: Path,
) -> None:
    plan = build_plan(case_data(), owner="Vera", source_root=FIXTURE)
    write_package(plan, source_root=FIXTURE, output=tmp_path / "report")
    output = tmp_path / "report"
    assert (
        json.loads((output / "calculations.json").read_text()) == plan["calculations"]
    )
    assert (
        "base/2027-01/ebitda,base,2027-01,ebitda,-100,EUR"
        in (output / "calculations.csv").read_text()
    )
    receipt = json.loads((output / "execution_receipt.json").read_text())
    assert all(
        hashlib.sha256((output / row["path"]).read_bytes()).hexdigest() == row["sha256"]
        for row in receipt["outputs"]
    )
    validate_plan(plan, source_root=FIXTURE)


def test_no_debt_service_and_zero_revenue_do_not_invent_ratios() -> None:
    case = case_data()
    case["observations"], case["resolutions"], case["narrative"] = [], [], []
    case.pop("assessment")
    case["required_sections"] = ["financial"]
    row = case["financial"]["scenarios"][0]["schedule"][0]
    row["revenue"] = "0"
    row["interest_expense"] = "0"
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert plan["calculations"]["base/2027-01/dscr"]["value"] is None
    assert plan["calculations"]["base/2027-01/ebitda_margin"]["value"] is None
    assert plan["calculations"]["base/2027-01/break_even_revenue"]["value"] is None


def test_partial_result_cannot_export_pdf(tmp_path: Path) -> None:
    case = case_data()
    case["resolutions"] = []
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    with pytest.raises(PlanningError, match="complete validated report"):
        export_pdf(plan, source_root=FIXTURE, output=tmp_path / "report.pdf")


def test_clara_registered_entrypoint_compiles_shared_case(tmp_path: Path) -> None:
    case = case_data()
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
    assert completed.returncode == 0, completed.stderr
    plan = json.loads((output / "business_plan.json").read_text())
    assert plan["workflow_id"] == "business-planning"
    assert (
        plan["calculations"]
        == build_plan(case, owner="Vera", source_root=FIXTURE)["calculations"]
    )


def test_vera_registered_entrypoint_binds_every_source_receipt(tmp_path: Path) -> None:
    ledger = _load_customer_ledger()
    client_root = tmp_path / "Customer"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Planning")
    case = case_data()
    imported_ids = []
    for source in case["sources"]:
        imported = ledger.import_document(
            client_root,
            client_id,
            engagement["engagement_id"],
            FIXTURE / source["path"],
            "source",
        )
        receipt = imported["receipt"]
        imported_ids.append(receipt["input_id"])
        source["path"] = f"imports/{receipt['input_id']}/{receipt['stored_name']}"
    input_case = tmp_path / "shared-case.json"
    input_case.write_text(json.dumps(case))
    imported = ledger.import_document(
        client_root, client_id, engagement["engagement_id"], input_case, "source"
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "business-planning",
        "0.1.0",
        input_ids=[imported["receipt"]["input_id"], *imported_ids],
    )
    running = ledger.start_run(
        client_root, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    bindings = running["context"]["input_bindings"]
    case_path = next(
        Path(b["path"])
        for b in bindings
        if b["binding_id"] == imported["receipt"]["input_id"]
    )
    output = Path(running["output_dir"]) / "plan"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "run_business_plan.py"),
            "--case",
            str(case_path),
            "--source-root",
            running["context"]["input_dir"],
            "--output-dir",
            str(output),
            "--client-engagement",
            running["context_path"],
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    plan = json.loads((output / "business_plan.json").read_text())
    assert plan["workflow_id"] == "business-planning"
    assert plan["calculations"]["base/2027-01/ebitda"]["value"] == "-100"


@pytest.mark.parametrize(
    "stage",
    [
        "Startup before commercial launch",
        "New venture within an existing firm",
        "Established trading company",
    ],
)
def test_stage_changes_context_without_changing_calculation_contract(
    stage: str,
) -> None:
    case = case_data()
    case["company_stage"] = stage
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert plan["status"] == "ready_for_professional_review"
    assert plan["calculations"]["base/2027-01/ebitda"]["value"] == "-100"


def test_complete_accepted_funding_recommendation_uses_full_horizon_gap() -> None:
    case = case_data()
    case["narrative"].append(
        {
            "id": "funding",
            "kind": "capital_recommendation",
            "text": "The modeled funding requirement is {{amount}}; timing must address the early cash deficit.",
            "claims": {
                "amount": {
                    "calculation_id": "base/2027-03/funding_requirement",
                    "value": "330",
                }
            },
            "basis_ids": ["cash-timing"],
            "rubric_id": None,
            "review": case["review"],
        }
    )
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert plan["status"] == "ready_for_professional_review"
    assert plan["accepted_narrative"][-1]["kind"] == "capital_recommendation"


def test_reported_ebitda_reference_cannot_bypass_adjusted_narrative_guard() -> None:
    case = case_data()
    case["narrative"][0]["claims"]["ebitda"] = {
        "calculation_id": "base/2027-01/reported_ebitda_client-ebitda",
        "value": "200",
    }
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert plan["status"] != "ready_for_professional_review"
    assert "profit-risk" not in {n["id"] for n in plan["accepted_narrative"]}


def test_reviewed_rubric_allows_supported_kpi_interpretation() -> None:
    case = case_data()
    case["assumptions"][0][
        "rubric"
    ] = "Professional hypothesis: review operating EBITDA as a monitored KPI; no rating scale is asserted."
    case["narrative"][0].update(kind="kpi", rubric_id="cash-timing")
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert plan["status"] == "ready_for_professional_review"
    assert plan["accepted_narrative"][0]["kind"] == "kpi"


def test_missing_review_timezone_prevents_readiness() -> None:
    case = case_data()
    case["review"]["reviewed_at"] = "2026-09-05T12:00:00"
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert plan["status"] == "partial"


def test_numeric_literal_in_strategic_prose_is_rejected() -> None:
    case = case_data()
    case["narrative"][0]["text"] = "The EBITDA is 200."
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    assert plan["status"] == "partial"
    assert "profit-risk" not in {n["id"] for n in plan["accepted_narrative"]}


def test_internal_only_classification_cannot_be_overridden_by_audience_lists() -> None:
    case = case_data()
    case["audience"] = "bank"
    for source in case["sources"]:
        source["intended_audience"].append("bank")
        source["confidentiality"]["allowed_audiences"].append("bank")
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    with pytest.raises(PlanningError, match="Audience restriction"):
        compile_html(plan, source_root=FIXTURE)


def test_failed_optional_pdf_preserves_validated_html_and_failure_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable_pdf(*args: object, **kwargs: object) -> None:
        raise PlanningError("Synthetic browser unavailable")

    monkeypatch.setattr(REPORT_MODULE, "export_pdf", unavailable_pdf)
    plan = build_plan(case_data(), owner="Vera", source_root=FIXTURE)
    with pytest.raises(PlanningError, match="Synthetic browser unavailable"):
        write_package(plan, source_root=FIXTURE, output=tmp_path / "report", pdf=True)
    receipt = json.loads((tmp_path / "report/execution_receipt.json").read_text())
    assert receipt["status"] == "partial"
    assert receipt["pdf_error"] == "Synthetic browser unavailable"
    assert (tmp_path / "report/business_plan_review.html").is_file()


@pytest.mark.parametrize("unit,accepted", [("ratio", True), ("EUR", False)])
def test_source_margin_observations_require_matching_calculation_units(
    unit: str, accepted: bool
) -> None:
    case = case_data()
    case["observations"].append(
        {
            "id": "reviewed-margin",
            "scenario": "base",
            "period": "2027-01",
            "metric": "ebitda_margin",
            "value": "-0.1",
            "unit": unit,
            "source_ids": ["review"],
            "basis": "adjusted",
            "material": True,
        }
    )
    if accepted:
        plan = build_plan(case, owner="Vera", source_root=FIXTURE)
        assert plan["status"] == "ready_for_professional_review"
    else:
        with pytest.raises(PlanningError, match="unit mismatch"):
            build_plan(case, owner="Vera", source_root=FIXTURE)


def channel_case() -> dict:
    case = case_data()
    case["financial"]["channels"] = [
        {
            "id": "retail-january",
            "channel": "Retail",
            "scenario": "base",
            "period": "2027-01",
            "unit_label": "unit",
            "units": "10",
            "revenue": "500",
            "variable_costs": "300",
            "input_refs": {
                "units": ["cash-timing"],
                "revenue": ["cash-timing"],
                "variable_costs": ["cash-timing"],
            },
        },
        {
            "id": "direct-january",
            "channel": "Direct",
            "scenario": "base",
            "period": "2027-01",
            "unit_label": "unit",
            "units": "20",
            "revenue": "500",
            "variable_costs": "300",
            "input_refs": {
                "units": ["cash-timing"],
                "revenue": ["cash-timing"],
                "variable_costs": ["cash-timing"],
            },
        },
    ]
    return case


def test_reconciled_channels_produce_canonical_unit_economics_chart() -> None:
    case = channel_case()
    case["assessment"]["charts"].append(
        {
            "chart_id": "unit-economics-base-2027-01",
            "section": "economics",
            "caption_id": "profit-risk",
        }
    )
    plan = build_plan(case, owner="Clara", source_root=FIXTURE)
    rendered = compile_html(plan, source_root=FIXTURE)
    assert plan["status"] == "ready_for_professional_review"
    assert (
        plan["calculations"][
            "base/2027-01/channel_retail-january_contribution_per_unit"
        ]["value"]
        == "20"
    )
    assert (
        plan["calculations"][
            "base/2027-01/channel_direct-january_contribution_per_unit"
        ]["value"]
        == "10"
    )
    assert 'id="unit-economics-base-2027-01"' in rendered
    assert "EUR/unit" in rendered


def test_channel_revenue_must_reconcile_to_authoritative_scenario() -> None:
    case = channel_case()
    case["financial"]["channels"][0]["revenue"] = "600"
    with pytest.raises(PlanningError, match="Channel revenue does not reconcile"):
        build_plan(case, owner="Vera", source_root=FIXTURE)


def test_zero_channel_units_do_not_invent_unit_economics() -> None:
    case = channel_case()
    case["financial"]["channels"][0]["units"] = "0"
    plan = build_plan(case, owner="Vera", source_root=FIXTURE)
    assert (
        plan["calculations"][
            "base/2027-01/channel_retail-january_contribution_per_unit"
        ]["value"]
        is None
    )


def test_incomplete_scenario_preserves_independently_complete_scenario() -> None:
    case = case_data()
    complete = deepcopy(case["financial"]["scenarios"][0])
    complete["id"] = "complete"
    complete["label"] = "Independent complete scenario"
    case["financial"]["scenarios"].append(complete)
    case["financial"]["scenarios"][0]["schedule"][1]["debt_repayments"] = None

    plan = build_plan(case, owner="Vera", source_root=FIXTURE)

    assert plan["status"] == "partial"
    assert "complete/2027-03/funding_requirement" in plan["calculations"]
    assert "base/2027-03/funding_requirement" not in plan["calculations"]
    assert plan["statements"]["unavailable_scenarios"] == ["base"]
