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
PLUGIN_ROOT = ROOT / "plugins" / "startup-business-plan"
SCRIPT_ROOT = PLUGIN_ROOT / "scripts"
SHARED_MODULES = ROOT / "plugins" / "_shared" / "vendor" / "modules"
if str(SHARED_MODULES) not in sys.path:
    sys.path.insert(0, str(SHARED_MODULES))


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CORE = _load_module(
    "test_vera_startup_business_plan_core",
    SCRIPT_ROOT / "business_planning_core.py",
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
        "venture_stage": "Early-revenue startup with a reviewed pilot",
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
        "test_vera_startup_business_plan_customer_ledger",
        ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py",
    )


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
        "startup-business-plan",
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
    assert plan["venture_stage"] == "Early-revenue startup with a reviewed pilot"
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
        (lambda case: case.update(venture_stage=""), "must be non-empty"),
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
        "commentary_template.json",
        "execution_receipt.json",
        "model_context.json",
        "reconciliation.json",
    }
    assert {path.name for path in output_dir.iterdir()} == expected
    receipt = json.loads(
        (output_dir / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["workflow_id"] == "startup-business-plan"
    assert receipt["status"] == "ready_for_professional_review"
    assert {item["path"] for item in receipt["outputs"]} == expected - {
        "execution_receipt.json"
    }
