from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "business-planning"
SCRIPT_ROOT = PLUGIN_ROOT / "scripts"
SHARED_MODULES = ROOT / "plugins" / "_shared" / "vendor" / "modules"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SHARED_MODULES) not in sys.path:
    sys.path.insert(0, str(SHARED_MODULES))


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HANDOFF = _load_module(
    "business_planning_handoff",
    SCRIPT_ROOT / "business_planning_handoff.py",
)
CORE = _load_module(
    "test_business_planning_financial_core",
    SCRIPT_ROOT / "business_planning_core.py",
)
STRATEGIC = _load_module(
    "test_business_planning_strategic_core",
    SCRIPT_ROOT / "strategic_planning_core.py",
)


def _case(*, evidence_status: str = "confirmed") -> dict[str, Any]:
    periods = ["2027-Q1", "2027-Q2"]
    schedule = [
        {
            "period": "2027-Q1",
            "assumption_ids": ["operating-case"],
            "revenue": "100",
            "cogs": "40",
            "operating_expenses": "30",
            "depreciation_amortization": "0",
            "interest_expense": "0",
            "tax_expense": "0",
            "capital_expenditure": "0",
            "ending_accounts_receivable": "20",
            "ending_inventory": "10",
            "ending_other_current_assets": "0",
            "ending_accounts_payable": "5",
            "ending_other_liabilities": "0",
            "debt_draws": "0",
            "debt_repayments": "0",
            "equity_contributions": "0",
            "dividends": "0",
        },
        {
            "period": "2027-Q2",
            "assumption_ids": ["operating-case"],
            "revenue": "120",
            "cogs": "48",
            "operating_expenses": "32",
            "depreciation_amortization": "0",
            "interest_expense": "0",
            "tax_expense": "0",
            "capital_expenditure": "0",
            "ending_accounts_receivable": "25",
            "ending_inventory": "12",
            "ending_other_current_assets": "0",
            "ending_accounts_payable": "6",
            "ending_other_liabilities": "0",
            "debt_draws": "0",
            "debt_repayments": "0",
            "equity_contributions": "0",
            "dividends": "0",
        },
    ]
    return {
        "schema_version": CORE.CASE_SCHEMA,
        "case_id": "venture-plan-2027",
        "entity_name": "Venture S.r.l.",
        "company_stage": "Early-revenue startup with a reviewed pilot",
        "planning_objective": "Assess funding needs and operating runway.",
        "professional_lens": "accounting_financial",
        "audience": "Board and financing bank",
        "reporting_currency": "EUR",
        "periods": periods,
        "reconciliation_tolerance": "0.01",
        "review": {
            "status": "reviewed",
            "reviewer": "Dott.ssa Rossi",
            "reviewed_at": "2026-08-27T12:00:00+02:00",
        },
        "evidence_register": [
            {
                "id": "opening-position",
                "kind": "opening_fact",
                "description": "Confirmed cash contribution at incorporation.",
                "source_ref": "source/opening-position.pdf",
                "status": "confirmed",
            },
            {
                "id": "commercial-basis",
                "kind": "management_assumption",
                "description": "Confirmed operating schedule for the planning horizon.",
                "source_ref": "review/assumption-readback.json",
                "status": evidence_status,
            },
        ],
        "opening_balance": {
            "values": {
                "cash": "100",
                "accounts_receivable": "0",
                "inventory": "0",
                "other_current_assets": "0",
                "net_fixed_assets": "0",
                "other_non_current_assets": "0",
                "accounts_payable": "0",
                "debt": "0",
                "other_liabilities": "0",
                "equity": "100",
            },
            "evidence_ids": ["opening-position"],
        },
        "assumptions": [
            {
                "id": "operating-case",
                "category": "commercial and operating schedule",
                "description": "Revenue, margin, costs, and working-capital balances.",
                "evidence_ids": ["commercial-basis"],
                "effective_periods": periods,
                "rationale": "Confirmed by management for this scenario.",
                "status": "confirmed",
            }
        ],
        "scenarios": [
            {
                "id": "base",
                "label": "Base case",
                "schedule": schedule,
            }
        ],
    }


def _load_customer_ledger() -> ModuleType:
    return _load_module(
        "test_business_planning_customer_ledger",
        ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py",
    )


def _strategic_case(*, evidence_status: str = "reviewed") -> dict[str, Any]:
    return {
        "schema_version": STRATEGIC.CASE_SCHEMA,
        "case_id": "strategy-plan-2027",
        "entity_name": "Example Group S.p.A.",
        "company_stage": "Established manufacturer entering an adjacent market",
        "planning_objective": "Choose the growth route and sequence execution.",
        "audience": "Board and shareholders",
        "planning_horizon": "2027 to 2029",
        "professional_lens": "strategic_commercial",
        "review": {
            "status": "reviewed",
            "reviewer": "Senior Partner",
            "reviewed_at": "2026-08-27T15:00:00+02:00",
        },
        "evidence_register": [
            {
                "id": "customer-research",
                "kind": "market_evidence",
                "description": "Reviewed customer interviews and segment evidence.",
                "source_ref": "sources/customer-research.pdf",
                "status": evidence_status,
            }
        ],
        "assumptions": [
            {
                "id": "channel-capacity",
                "category": "commercial execution",
                "description": "The current sales team can cover the first launch wave.",
                "evidence_ids": ["customer-research"],
                "rationale": "Confirmed by management for planning purposes.",
                "status": "confirmed",
            }
        ],
        "findings": [
            {
                "id": "segment-fit",
                "domain": "Market and customer",
                "statement": "The adjacent segment values the company's service model.",
                "implication": "Test a focused offer before broad expansion.",
                "evidence_ids": ["customer-research"],
                "assumption_ids": ["channel-capacity"],
                "confidence": "medium",
            }
        ],
        "options": [
            {
                "id": "focused-launch",
                "title": "Focused segment launch",
                "description": "Launch one offer in the strongest evidenced segment.",
                "benefits": ["Limits execution complexity."],
                "drawbacks": ["Delays broader coverage."],
                "evidence_ids": ["customer-research"],
                "assumption_ids": ["channel-capacity"],
            }
        ],
        "recommendation": {
            "statement": "Run the focused launch subject to the stated conditions.",
            "option_ids": ["focused-launch"],
            "evidence_ids": ["customer-research"],
            "assumption_ids": ["channel-capacity"],
            "conditions": ["Validate repeat demand before national rollout."],
        },
        "initiatives": [
            {
                "id": "pilot-launch",
                "title": "Pilot the focused offer",
                "objective": "Test demand and delivery economics in one segment.",
                "owner": "Commercial director",
                "milestones": [
                    {"period": "2027-Q1", "outcome": "Offer and target list approved."}
                ],
                "kpis": ["Qualified pipeline", "Conversion rate"],
                "evidence_ids": ["customer-research"],
                "assumption_ids": ["channel-capacity"],
            }
        ],
        "risks": [
            {
                "id": "sales-overload",
                "description": "The existing team may not absorb the launch workload.",
                "response": "Use a stage gate before widening the target list.",
                "evidence_ids": ["customer-research"],
                "assumption_ids": ["channel-capacity"],
            }
        ],
        "open_questions": [
            {
                "id": "pricing-proof",
                "question": "What price sustains repeat demand?",
                "why_it_matters": "It changes the commercial case and Vera handoff.",
            }
        ],
    }


def _aligned_strategic_case() -> dict[str, Any]:
    case = _strategic_case()
    case["case_id"] = "venture-plan-2027"
    case["entity_name"] = "Venture S.r.l."
    case["assumptions"][0]["id"] = "operating-case"
    case["assumptions"][0][
        "description"
    ] = "Revenue, margin, costs, and working-capital balances."
    for collection_name in ("findings", "options", "initiatives", "risks"):
        for item in case[collection_name]:
            item["assumption_ids"] = ["operating-case"]
    case["recommendation"]["assumption_ids"] = ["operating-case"]
    return case


def _clara_workspace(tmp_path: Path, case: dict[str, Any]) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "clara-case"
    workspace.mkdir()
    workspace_files = {
        "case_manifest.json": {
            "schema_version": 1,
            "client": case["entity_name"],
            "project": "Business planning",
            "objective": case["planning_objective"],
            "audience": case["audience"],
            "status": "active",
        },
        "material_registry.json": {"schema_version": 1, "materials": []},
        "judgement_log.json": {"schema_version": 1, "entries": []},
        "open_questions.json": {"schema_version": 1, "questions": []},
        "case_issues.json": {"schema_version": 1, "issues": []},
        "clara_mandate.json": {"schema_version": 1},
    }
    for filename, payload in workspace_files.items():
        (workspace / filename).write_text(json.dumps(payload), encoding="utf-8")
    case_path = workspace / "strategic_business_plan_case.json"
    case_path.write_text(json.dumps(case), encoding="utf-8")
    return workspace, case_path, workspace / "business-plan"


def _running_case(tmp_path: Path, case: dict[str, Any]) -> tuple[Path, Path, Path]:
    ledger = _load_customer_ledger()
    client_root = tmp_path / "Customer"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Planning")
    source = tmp_path / "business_plan_case.json"
    source.write_text(json.dumps(case), encoding="utf-8")
    imported = ledger.import_document(
        client_root,
        client_id,
        engagement["engagement_id"],
        source,
        "source",
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "business-planning",
        "0.1.0",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client_root,
        engagement["engagement_id"],
        prepared["run"]["run_id"],
    )
    return (
        Path(running["context_path"]),
        Path(running["context"]["input_bindings"][0]["path"]),
        Path(running["output_dir"]),
    )


def test_startup_case_without_historical_actuals_builds_reconciled_plan() -> None:
    case = _case()

    plan = CORE.build_business_plan(case)

    assert "mode" not in case
    assert plan["company_stage"] == "Early-revenue startup with a reviewed pilot"
    assert plan["professional_lens"] == "accounting_financial"
    assert all(
        item["kind"] != "historical_actual" for item in case["evidence_register"]
    )
    assert plan["status"] == "ready_for_professional_review"
    assert plan["reconciliation"]["all_passed"] is True
    assert plan["scenarios"][0]["summary"] == {
        "total_revenue": "220",
        "total_net_income": "70",
        "ending_cash": "139",
        "minimum_cash": "105",
        "funding_requirement": "0",
        "total_debt_draws": "0",
        "total_equity_contributions": "0",
        "break_even_period": "2027-Q1",
    }


def test_negative_cash_is_preserved_as_funding_requirement() -> None:
    case = _case()
    case["scenarios"][0]["schedule"][0]["operating_expenses"] = "250"

    plan = CORE.build_business_plan(case)

    summary = plan["scenarios"][0]["summary"]
    assert summary["minimum_cash"] == "-115"
    assert summary["funding_requirement"] == "115"
    assert plan["reconciliation"]["all_passed"] is True


def test_reconciled_negative_opening_equity_is_supported() -> None:
    case = _case()
    case["opening_balance"]["values"].update(
        cash="0",
        accounts_payable="50",
        equity="-50",
    )

    plan = CORE.build_business_plan(case)

    assert plan["opening_balance"]["values"]["equity"] == "-50"
    assert plan["reconciliation"]["all_passed"] is True


def test_unverified_referenced_evidence_keeps_result_partial() -> None:
    plan = CORE.build_business_plan(_case(evidence_status="unverified"))

    assert plan["status"] == "partial"
    assert plan["evidence_coverage"]["unverified_evidence_ids"] == ["commercial-basis"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda case: case["review"].update(status="draft"), "must be reviewed"),
        (
            lambda case: case["assumptions"][0].update(status="proposed"),
            "status=confirmed",
        ),
        (
            lambda case: case["assumptions"][0].update(effective_periods=["2027-Q1"]),
            "inactive assumptions",
        ),
        (
            lambda case: case["review"].update(reviewed_at="2026-08-27"),
            "must include a timezone",
        ),
        (lambda case: case.update(mode="startup"), "fields do not match"),
        (lambda case: case.update(company_stage=""), "must be non-empty"),
        (
            lambda case: case.update(professional_lens="strategic_commercial"),
            "must be accounting_financial",
        ),
    ),
)
def test_case_contract_rejects_unreviewed_or_hidden_routing_state(
    mutation: Any, message: str
) -> None:
    case = _case()
    mutation(case)

    with pytest.raises(CORE.BusinessPlanningContractError, match=message):
        CORE.build_business_plan(case)


def test_case_contract_rejects_confirmed_assumption_that_is_not_applied() -> None:
    case = _case()
    case["assumptions"].append(
        {
            "id": "unused-case",
            "category": "financing",
            "description": "Confirmed but not applied financing assumption.",
            "evidence_ids": ["commercial-basis"],
            "effective_periods": ["2027-Q1"],
            "rationale": "Confirmed during review.",
            "status": "confirmed",
        }
    )

    with pytest.raises(
        CORE.BusinessPlanningContractError, match="not applied by any scenario"
    ):
        CORE.build_business_plan(case)


def test_model_context_excludes_internal_source_references() -> None:
    plan = CORE.build_business_plan(_case())

    model_context = CORE.build_model_context(plan)

    serialized = json.dumps(model_context)
    assert '"source_ref":' not in serialized
    assert "opening-position.pdf" not in serialized
    assert "raw source populations" in model_context["excluded_by_default"]


def test_runner_writes_complete_client_bound_review_package(tmp_path: Path) -> None:
    context_path, case_path, output_dir = _running_case(tmp_path, _case())

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "run_business_plan.py"),
            "--case",
            str(case_path),
            "--client-engagement",
            str(context_path),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    expected = {
        "assumption_ledger.csv",
        "business_plan.json",
        "business_plan.xlsx",
        "business_plan_facts.md",
        "business_plan_review.html",
        "business_planning_handoff.json",
        "commentary_template.json",
        "execution_receipt.json",
        "model_context.json",
        "reconciliation.json",
    }
    assert {path.name for path in output_dir.iterdir()} == expected
    receipt = json.loads(
        (output_dir / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["workflow_id"] == "business-planning"
    assert receipt["status"] == "ready_for_professional_review"
    assert {item["path"] for item in receipt["outputs"]} == expected - {
        "execution_receipt.json"
    }


def test_established_company_uses_the_same_financial_contract() -> None:
    case = _case()
    case["company_stage"] = "Established manufacturer with five reviewed years"
    case["planning_objective"] = (
        "Fund a capacity expansion from operating cash and debt."
    )
    case["evidence_register"][0]["kind"] = "historical_actual"

    plan = CORE.build_business_plan(case)
    handoff = CORE.build_counterpart_handoff(plan)

    assert plan["status"] == "ready_for_professional_review"
    assert plan["company_stage"].startswith("Established manufacturer")
    assert handoff["from_product"] == "Vera"
    assert handoff["to_product"] == "Clara"
    assert handoff["status"] == "ready_for_counterpart_review"


def test_clara_strategic_case_keeps_semantic_content_model_led() -> None:
    plan = STRATEGIC.build_strategic_plan(_strategic_case())
    handoff = STRATEGIC.build_counterpart_handoff(plan)

    assert plan["professional_lens"] == "strategic_commercial"
    assert plan["recommendation"]["option_ids"] == ["focused-launch"]
    assert plan["status"] == "ready_for_professional_review"
    assert handoff["from_product"] == "Clara"
    assert handoff["to_product"] == "Vera"
    assert handoff["assumptions"][0]["id"] == "channel-capacity"


def test_clara_strategic_case_supports_a_startup_without_a_second_mode() -> None:
    case = _strategic_case()
    case["company_stage"] = "Pre-revenue startup with a reviewed prototype"
    case["entity_name"] = "New Venture S.r.l."

    plan = STRATEGIC.build_strategic_plan(case)

    assert "mode" not in case
    assert plan["company_stage"].startswith("Pre-revenue startup")
    assert plan["status"] == "ready_for_professional_review"


def test_clara_strategic_case_rejects_wrong_lens() -> None:
    case = _strategic_case()
    case["professional_lens"] = "accounting_financial"

    with pytest.raises(
        STRATEGIC.StrategicPlanningContractError,
        match="must be strategic_commercial",
    ):
        STRATEGIC.build_strategic_plan(case)


def test_clara_strategic_case_rejects_unknown_option_reference() -> None:
    case = _strategic_case()
    case["recommendation"]["option_ids"] = ["missing-option"]

    with pytest.raises(
        STRATEGIC.StrategicPlanningContractError,
        match="unknown references",
    ):
        STRATEGIC.build_strategic_plan(case)


def test_clara_strategic_case_rejects_unlinked_assumption() -> None:
    case = _strategic_case()
    case["assumptions"][0]["evidence_ids"] = []

    with pytest.raises(
        STRATEGIC.StrategicPlanningContractError,
        match="evidence_ids must not be empty",
    ):
        STRATEGIC.build_strategic_plan(case)


@pytest.mark.parametrize(
    "target",
    ("finding", "option", "recommendation", "initiative", "risk"),
)
def test_clara_strategic_case_rejects_unsupported_plan_element(target: str) -> None:
    case = _strategic_case()
    item = (
        case["recommendation"] if target == "recommendation" else case[f"{target}s"][0]
    )
    item["evidence_ids"] = []
    item["assumption_ids"] = []

    with pytest.raises(
        STRATEGIC.StrategicPlanningContractError,
        match="must reference evidence or a confirmed assumption",
    ):
        STRATEGIC.build_strategic_plan(case)


def test_counterpart_handoff_reports_alignment_and_description_divergence() -> None:
    financial_plan = CORE.build_business_plan(_case())
    handoff = CORE.build_counterpart_handoff(financial_plan)
    strategic_case = _aligned_strategic_case()

    aligned = HANDOFF.review_counterpart_handoff(
        strategic_case,
        handoff,
        receiving_product="Clara",
    )
    strategic_case["assumptions"][0]["description"] = "A different description."
    divergent = HANDOFF.review_counterpart_handoff(
        strategic_case,
        handoff,
        receiving_product="Clara",
    )

    assert aligned["status"] == "aligned_for_counterpart_use"
    assert divergent["status"] == "divergence_requires_professional_review"
    assert divergent["assumption_comparison"]["description_divergences"] == [
        {
            "assumption_id": "operating-case",
            "counterpart_description": (
                "Revenue, margin, costs, and working-capital balances."
            ),
            "receiving_case_description": "A different description.",
        }
    ]


def test_vera_reviews_aligned_clara_handoff() -> None:
    strategic_plan = STRATEGIC.build_strategic_plan(_aligned_strategic_case())
    handoff = STRATEGIC.build_counterpart_handoff(strategic_plan)

    review = HANDOFF.review_counterpart_handoff(
        _case(),
        handoff,
        receiving_product="Vera",
    )

    assert review["status"] == "aligned_for_counterpart_use"
    assert review["assumption_comparison"]["shared_assumption_ids"] == [
        "operating-case"
    ]


def test_blocked_financial_plan_produces_explicitly_blocked_handoff() -> None:
    case = _case()
    case["opening_balance"]["values"]["equity"] = "99"

    plan = CORE.build_business_plan(case)
    handoff = CORE.build_counterpart_handoff(plan)

    assert plan["status"] == "blocked"
    assert handoff["status"] == "blocked_source_plan"
    assert handoff["source_plan_status"] == "blocked"
    assert handoff["source_review_status"] == "draft_pending_professional_review"
    review = HANDOFF.review_counterpart_handoff(
        _aligned_strategic_case(),
        handoff,
        receiving_product="Clara",
    )
    assert review["status"] == "source_not_ready"


def test_clara_runner_writes_complete_strategic_review_package(tmp_path: Path) -> None:
    workspace, case_path, output_dir = _clara_workspace(tmp_path, _strategic_case())

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "run_strategic_plan.py"),
            "--case",
            str(case_path),
            "--output-dir",
            str(output_dir),
            "--case-workspace",
            str(workspace),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    expected = {
        "assumption_ledger.csv",
        "business_planning_handoff.json",
        "execution_receipt.json",
        "model_context.json",
        "strategic_business_plan.json",
        "strategic_business_plan.md",
        "strategic_business_plan_review.html",
    }
    assert {path.name for path in output_dir.iterdir()} == expected
    model_context = json.loads(
        (output_dir / "model_context.json").read_text(encoding="utf-8")
    )
    assert '"source_ref":' not in json.dumps(model_context)
    receipt = json.loads(
        (output_dir / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["professional_lens"] == "strategic_commercial"
    assert receipt["case_content_sha256"]


def test_clara_runner_rejects_output_outside_case_workspace(tmp_path: Path) -> None:
    workspace, case_path, _output_dir = _clara_workspace(tmp_path, _strategic_case())

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "run_strategic_plan.py"),
            "--case",
            str(case_path),
            "--output-dir",
            str(tmp_path / "outside"),
            "--case-workspace",
            str(workspace),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2
    assert "output directory must be <case-workspace>/business-plan" in completed.stderr


def test_clara_runner_records_aligned_vera_handoff(tmp_path: Path) -> None:
    case = _aligned_strategic_case()
    workspace, case_path, output_dir = _clara_workspace(tmp_path, case)
    handoff_path = workspace / "vera_business_planning_handoff.json"
    handoff_path.write_text(
        json.dumps(CORE.build_counterpart_handoff(CORE.build_business_plan(_case()))),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "run_strategic_plan.py"),
            "--case",
            str(case_path),
            "--output-dir",
            str(output_dir),
            "--case-workspace",
            str(workspace),
            "--counterpart-handoff",
            str(handoff_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    review = json.loads(
        (output_dir / "counterpart_handoff_review.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (output_dir / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert review["status"] == "aligned_for_counterpart_use"
    assert receipt["counterpart_handoff"]["review_status"] == (
        "aligned_for_counterpart_use"
    )


def test_review_html_exposes_complete_financial_and_strategic_surfaces() -> None:
    financial_html = CORE.render_html(CORE.build_business_plan(_case()))
    strategic_html = STRATEGIC.render_html(
        STRATEGIC.build_strategic_plan(_strategic_case())
    )

    for heading in (
        "Evidence coverage",
        "Confirmed assumptions",
        "Integrated statements",
        "Reconciliation",
    ):
        assert heading in financial_html
    for heading in (
        "Evidence register",
        "Confirmed assumptions",
        "Options and trade-offs",
        "Risks and responses",
        "Open questions",
    ):
        assert heading in strategic_html
    assert "customer-research" in strategic_html
    assert "Validate repeat demand before national rollout." in strategic_html


def test_unverified_strategic_evidence_keeps_result_partial() -> None:
    plan = STRATEGIC.build_strategic_plan(_strategic_case(evidence_status="unverified"))

    assert plan["status"] == "partial"
    assert plan["evidence_coverage"]["unverified_evidence_ids"] == ["customer-research"]
