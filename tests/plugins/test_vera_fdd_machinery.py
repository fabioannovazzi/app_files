from __future__ import annotations

import hashlib
import json
import re
import sys
from copy import deepcopy
from decimal import localcontext
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.plugins._financial_analysis_test_loader import (
    load_financial_analysis_scripts,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "plugins" / "_shared" / "vendor" / "modules"
SCRIPT_ROOT = ROOT / "plugins" / "financial-analysis" / "scripts"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

FINANCIAL_SCRIPTS = load_financial_analysis_scripts(SCRIPT_ROOT)
canonical_json_sha256 = FINANCIAL_SCRIPTS.kernel.canonical_json_sha256
prepare_fdd_case = FINANCIAL_SCRIPTS.fdd_runner.prepare_fdd_case
PACKS = FINANCIAL_SCRIPTS.pack_runner.PACKS
PackRunError = FINANCIAL_SCRIPTS.pack_runner.PackRunError
run_pack = FINANCIAL_SCRIPTS.pack_runner.run_pack
from vera_financial_analysis import (
    FDDContractError,
    build_contingent_liability_register,
    build_data_package_manifest,
    build_dataset_contract,
    build_fdd_case,
    build_fdd_metric_receipt,
    build_financial_issue_register,
    execute_fdd_case,
    validate_contingent_liability_register,
    validate_fdd_calculation_result,
    validate_fdd_case,
    validate_fdd_metric_receipt,
    validate_financial_issue_register,
)

CASE_ID = "case.synthetic"
SCOPE_ID = "scope.synthetic"
ENTITY_REFS = ["entity.synthetic"]
CURRENCY = "EUR"
UNIT = "EUR_units"
PERIOD = {"start": "2025-01-01", "end": "2025-12-31"}
ARTIFACT_REF = "artifact.source"
DATASET_REF = "dataset.source.v1"


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    content = {key: item for key, item in value.items() if key != "content_sha256"}
    return {**content, "content_sha256": canonical_json_sha256(content)}


def _review() -> dict[str, str]:
    return {
        "status": "reviewed",
        "reviewed_on": "2026-07-28",
        "reviewer_ref": "reviewer.synthetic",
        "basis": "Reviewed synthetic fixture.",
    }


def _decisions() -> list[dict[str, str]]:
    return [
        {
            "decision_ref": "decision.synthetic",
            **_review(),
        }
    ]


def _source_artifacts(package: dict[str, Any]) -> list[dict[str, Any]]:
    source = package["sources"][0]
    return [
        {
            "artifact_ref": source["artifact_ref"],
            "dataset_contract_ref": source["dataset_contract_ref"],
            "role": "source_evidence",
            "byte_count": source["byte_count"],
            "sha256": source["sha256"],
        }
    ]


def _context(
    tmp_path: Path, *, package_id: str = "package.synthetic.v1"
) -> dict[str, Any]:
    source_path = tmp_path / "source.txt"
    source_path.write_text("synthetic reviewed evidence\n", encoding="utf-8")
    source_bytes = source_path.read_bytes()
    package = build_data_package_manifest(
        package_id=package_id,
        snapshot_id=f"{package_id}.snapshot",
        reporting_perimeter={
            "entity_refs": ENTITY_REFS,
            "period_start": PERIOD["start"],
            "period_end": PERIOD["end"],
            "currency_refs": [CURRENCY],
        },
        sensitivity="confidential",
        sources=[
            {
                "source_id": "source.synthetic",
                "artifact_ref": ARTIFACT_REF,
                "file_name": source_path.name,
                "locator": source_path.name,
                "byte_count": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "snapshot_id": f"{package_id}.snapshot",
                "dataset_contract_ref": DATASET_REF,
            }
        ],
    )
    dataset = build_dataset_contract(
        dataset_contract_id=DATASET_REF,
        dataset_id="source",
        version="v1",
        grain="one reviewed source row",
        keys=["row_id"],
        fields=[
            {
                "name": "row_id",
                "concept_id": "row.identity",
                "data_type": "text",
                "nullable": False,
                "unit": "identifier",
                "currency": None,
                "aggregation": "none",
                "period_role": "none",
            },
            {
                "name": "amount",
                "concept_id": "financial.amount",
                "data_type": "decimal",
                "nullable": False,
                "unit": UNIT,
                "currency": CURRENCY,
                "aggregation": "sum",
                "period_role": "period_end",
            },
        ],
        period={
            "calendar": "gregorian",
            "grain": "month",
            "start": PERIOD["start"],
            "end": PERIOD["end"],
        },
        source_artifact_refs=[ARTIFACT_REF],
    )
    return {"package": package, "datasets": [dataset]}


def _build_case(
    context: dict[str, Any],
    *,
    pack_id: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    return build_fdd_case(
        case_id=CASE_ID,
        scope_id=SCOPE_ID,
        entity_refs=ENTITY_REFS,
        pack_id=pack_id,
        currency=CURRENCY,
        unit=UNIT,
        reporting_period=PERIOD,
        package=context["package"],
        datasets=context["datasets"],
        request_id=f"request.{pack_id}.v1",
        review=_review(),
        reviewed_decisions=_decisions(),
        inputs=inputs,
    )


def _qoe_inputs(
    *,
    reported: str = "1000",
    adjustment: str = "100",
) -> dict[str, Any]:
    return {
        "reported_ebitda": {
            "amount": reported,
            "evidence_refs": [ARTIFACT_REF],
        },
        "adjustments": [
            {
                "adjustment_id": "adjustment.one",
                "economic_effect_id": "effect.ebitda.one",
                "description": "Reviewed adjustment.",
                "category_id": "category.reviewed",
                "period_start": PERIOD["start"],
                "period_end": PERIOD["end"],
                "ebitda_impact": adjustment,
                "included": True,
                "decision_ref": "decision.synthetic",
                "cash_effect": "not_assessed",
                "evidence_refs": [ARTIFACT_REF],
            }
        ],
    }


def _net_debt_inputs() -> dict[str, Any]:
    return {
        "as_of_date": PERIOD["end"],
        "items": [
            {
                "item_id": "item.cash",
                "economic_effect_id": "effect.cash",
                "description": "Cash.",
                "as_of_date": PERIOD["end"],
                "classification": "cash",
                "amount": "100",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
            {
                "item_id": "item.debt",
                "economic_effect_id": "effect.debt",
                "description": "Debt.",
                "as_of_date": PERIOD["end"],
                "classification": "debt",
                "amount": "500",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
            {
                "item_id": "item.debt_like",
                "economic_effect_id": "effect.debt_like",
                "description": "Debt-like item.",
                "as_of_date": PERIOD["end"],
                "classification": "debt_like",
                "amount": "50",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
        ],
    }


def _working_capital_inputs() -> dict[str, Any]:
    return {
        "average_scale": 2,
        "closing_period": "2025-12",
        "monthly_balances": [
            {
                "period": "2025-01",
                "period_end": "2025-01-31",
                "reported_operating_nwc": "100",
                "included_in_average": True,
                "evidence_refs": [ARTIFACT_REF],
            },
            {
                "period": "2025-12",
                "period_end": PERIOD["end"],
                "reported_operating_nwc": "120",
                "included_in_average": True,
                "evidence_refs": [ARTIFACT_REF],
            },
        ],
        "normalization_adjustments": [
            {
                "adjustment_id": "adjustment.nwc",
                "economic_effect_id": "effect.nwc",
                "period": "2025-12",
                "description": "Reviewed NWC normalization.",
                "category_id": "category.normalization",
                "nwc_impact": "10",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            }
        ],
        "selected_target": {
            "economic_effect_id": "effect.nwc.target",
            "amount": "105",
            "basis": "Reviewed target.",
            "decision_ref": "decision.synthetic",
            "evidence_refs": [ARTIFACT_REF],
        },
    }


def _capex_inputs() -> dict[str, Any]:
    return {
        "items": [
            {
                "capex_id": "capex.cash",
                "economic_effect_id": "effect.capex.cash",
                "period": "2025",
                "period_start": PERIOD["start"],
                "period_end": PERIOD["end"],
                "description": "Cash Capex.",
                "measurement_basis": "cash_paid",
                "classification": "maintenance",
                "amount": "60",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
            {
                "capex_id": "capex.addition",
                "economic_effect_id": "effect.capex.addition",
                "period": "2025",
                "period_start": PERIOD["start"],
                "period_end": PERIOD["end"],
                "description": "Asset addition.",
                "measurement_basis": "asset_addition",
                "classification": "growth",
                "amount": "100",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
        ]
    }


def _metric_map(result: dict[str, Any]) -> dict[str, str]:
    return {item["metric_id"]: item["value"] for item in result["metrics"]}


def _bundle(case: dict[str, Any]) -> dict[str, Any]:
    stack = case["contract_stack"]
    return _seal(
        {
            "schema_version": "vera.fdd_execution_bundle.v2",
            "package": stack["package"],
            "datasets": stack["datasets"],
            "relationships": stack["relationships"],
            "crosswalks": stack["crosswalks"],
            "request": stack["request"],
            "fdd_case": case,
        }
    )


def test_financial_script_loader_restores_existing_kernel_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = ModuleType("preparation_contract_kernel")
    monkeypatch.setitem(sys.modules, "preparation_contract_kernel", sentinel)

    loaded = load_financial_analysis_scripts(SCRIPT_ROOT)

    assert loaded.kernel is not sentinel
    assert (
        Path(loaded.kernel.__file__).resolve()
        == (SCRIPT_ROOT / "preparation_contract_kernel.py").resolve()
    )
    assert sys.modules["preparation_contract_kernel"] is sentinel


def test_fdd_calculation_packs_and_bridges_execute_exactly(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    qoe_case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    net_debt_case = _build_case(
        context,
        pack_id="net_debt",
        inputs=_net_debt_inputs(),
    )
    working_capital_case = _build_case(
        context,
        pack_id="normalized_working_capital",
        inputs=_working_capital_inputs(),
    )
    capex_case = _build_case(
        context,
        pack_id="capex",
        inputs=_capex_inputs(),
    )
    qoe_result = execute_fdd_case(qoe_case)
    net_debt_result = execute_fdd_case(net_debt_case)
    working_capital_result = execute_fdd_case(working_capital_case)
    capex_result = execute_fdd_case(capex_case)
    qoe_receipt = build_fdd_metric_receipt(
        qoe_case,
        qoe_result,
        "adjusted_ebitda",
    )
    net_debt_receipt = build_fdd_metric_receipt(
        net_debt_case,
        net_debt_result,
        "net_debt",
    )
    working_capital_receipt = build_fdd_metric_receipt(
        working_capital_case,
        working_capital_result,
        "closing_vs_target_adjustment",
    )
    capex_receipt = build_fdd_metric_receipt(
        capex_case,
        capex_result,
        "capex.cash_paid.total",
    )
    deal_case = _build_case(
        context,
        pack_id="deal_bridges",
        inputs={
            "upstream_metrics": [
                qoe_receipt,
                net_debt_receipt,
                working_capital_receipt,
                capex_receipt,
            ],
            "adjusted_ebitda_ref": qoe_receipt["receipt_id"],
            "enterprise_value": {
                "amount": "5000",
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
            "cash_bridge_items": [
                {
                    "bridge_item_id": "bridge.cash.capex",
                    "description": "Cash Capex.",
                    "category_id": "category.capex",
                    "economic_effect_refs": capex_receipt["economic_effect_refs"],
                    "cash_flow_impact": "-60",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "evidence_refs": [ARTIFACT_REF],
                    "upstream_metric_ref": capex_receipt["receipt_id"],
                    "upstream_multiplier": "-1",
                },
                {
                    "bridge_item_id": "bridge.cash.nwc",
                    "description": "Working-capital cash effect.",
                    "category_id": "category.nwc",
                    "economic_effect_refs": working_capital_receipt[
                        "economic_effect_refs"
                    ],
                    "cash_flow_impact": "-25",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "evidence_refs": [ARTIFACT_REF],
                    "upstream_metric_ref": working_capital_receipt["receipt_id"],
                    "upstream_multiplier": "-1",
                },
            ],
            "equity_bridge_items": [
                {
                    "bridge_item_id": "bridge.equity.net_debt",
                    "description": "Net debt.",
                    "category_id": "category.net_debt",
                    "economic_effect_refs": net_debt_receipt["economic_effect_refs"],
                    "equity_value_impact": "-450",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "evidence_refs": [ARTIFACT_REF],
                    "upstream_metric_ref": net_debt_receipt["receipt_id"],
                    "upstream_multiplier": "-1",
                },
                {
                    "bridge_item_id": "bridge.equity.nwc",
                    "description": "Working-capital adjustment.",
                    "category_id": "category.nwc",
                    "economic_effect_refs": working_capital_receipt[
                        "economic_effect_refs"
                    ],
                    "equity_value_impact": "25",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "evidence_refs": [ARTIFACT_REF],
                    "upstream_metric_ref": working_capital_receipt["receipt_id"],
                    "upstream_multiplier": "1",
                },
            ],
        },
    )
    deal_result = execute_fdd_case(deal_case)
    cases = {
        "quality_of_earnings": qoe_case,
        "net_debt": net_debt_case,
        "normalized_working_capital": working_capital_case,
        "capex": capex_case,
        "deal_bridges": deal_case,
    }
    for pack_id, case in cases.items():
        bundle_path = tmp_path / f"{pack_id}.json"
        bundle_path.write_text(
            json.dumps(_bundle(case), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt = run_pack(
            pack_id=pack_id,
            case_path=bundle_path,
            output_dir=tmp_path / f"{pack_id}-output",
        )
        assert receipt["status"] == "passed"
        assert receipt["schema_version"] == (
            "vera.financial_analysis_pack_execution.v3"
        )

    assert set(PACKS) == {
        "monthly_pnl",
        "working_capital",
        "customer_concentration",
        *cases,
    }
    assert _metric_map(qoe_result)["adjusted_ebitda"] == "1100"
    assert _metric_map(net_debt_result)["net_debt"] == "450"
    assert (
        _metric_map(working_capital_result)["candidate_average_normalized_nwc"] == "115"
    )
    assert _metric_map(working_capital_result)["closing_vs_target_adjustment"] == "25"
    assert _metric_map(capex_result)["capex.cash_paid.total"] == "60"
    assert _metric_map(deal_result)["cash_bridge_result"] == "1015"
    assert _metric_map(deal_result)["equity_value"] == "4575"
    assert deal_result["source_tie_out"]["status"] == "not_assessed"
    assert deal_result["report_ready"] is False


def test_fdd_exact_arithmetic_is_ambient_context_independent(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(
            reported="1234567890123456789012345678",
            adjustment="0.1",
        ),
    )

    results = []
    for precision in (10, 28, 60):
        with localcontext() as decimal_context:
            decimal_context.prec = precision
            results.append(execute_fdd_case(case))

    assert results[0] == results[1] == results[2]
    assert (
        _metric_map(results[0])["adjusted_ebitda"] == "1234567890123456789012345678.1"
    )


def test_fdd_runner_closes_files_contracts_and_replay(tmp_path: Path) -> None:
    context = _context(tmp_path)
    case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    bundle_path = tmp_path / "case.json"
    bundle_path.write_text(
        json.dumps(_bundle(case), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = prepare_fdd_case(
        bundle_path,
        first_dir,
        expected_pack_id="quality_of_earnings",
    )
    second = prepare_fdd_case(
        bundle_path,
        second_dir,
        expected_pack_id="quality_of_earnings",
    )

    assert first == second
    assert first["status"] == "passed"
    assert {path.name for path in first_dir.iterdir()} == {
        "fdd_line_items.json",
        "fdd_metrics.json",
        "fdd_result.json",
        "financial_analysis_contract_audit.json",
        "prepared_evidence_manifest.json",
        "reconciliation.json",
    }
    manifest = json.loads(
        (first_dir / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    line_items = json.loads(
        (first_dir / "fdd_line_items.json").read_text(encoding="utf-8")
    )
    assert line_items["schema_version"] == "vera.fdd_line_items.v2"
    assert manifest["schema_version"] == "vera.prepared_evidence_manifest.v2"
    assert manifest["report_ready"] is False


def test_fdd_runner_cannot_overwrite_bundle_source_or_symlink_output(
    tmp_path: Path,
) -> None:
    collision_dir = tmp_path / "collision"
    collision_dir.mkdir()
    context = _context(collision_dir)
    case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    bundle_path = collision_dir / "fdd_result.json"
    bundle_path.write_text(
        json.dumps(_bundle(case), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original_bundle = bundle_path.read_bytes()
    original_source = (collision_dir / "source.txt").read_bytes()

    with pytest.raises(ValueError, match="fresh and empty"):
        prepare_fdd_case(
            bundle_path,
            collision_dir,
            expected_pack_id="quality_of_earnings",
        )

    symlink_target = tmp_path / "real-output"
    symlink_target.mkdir()
    symlink_output = tmp_path / "symlink-output"
    symlink_output.symlink_to(symlink_target, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symlink"):
        prepare_fdd_case(
            bundle_path,
            symlink_output,
            expected_pack_id="quality_of_earnings",
        )

    bundle_symlink = tmp_path / "bundle-symlink.json"
    bundle_symlink.symlink_to(bundle_path)
    with pytest.raises(PackRunError, match="regular file"):
        run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_symlink,
            output_dir=tmp_path / "runner-output",
        )
    with pytest.raises(PackRunError, match="cannot be a symlink"):
        run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=symlink_output,
        )

    assert bundle_path.read_bytes() == original_bundle
    assert (collision_dir / "source.txt").read_bytes() == original_source


def test_mcp_pack_registry_matches_python_runner() -> None:
    server_text = (
        ROOT / "plugins" / "financial-analysis" / "mcp" / "server.cjs"
    ).read_text(encoding="utf-8")
    pack_match = re.search(r"const PACKS = (\[[\s\S]*?\]);", server_text)
    contract_match = re.search(r"const CONTRACTS = (\[[\s\S]*?\]);", server_text)

    assert pack_match is not None
    assert re.findall(r'"([^"]+)"', pack_match.group(1)) == list(PACKS)
    assert contract_match is not None
    assert re.findall(r'"([^"]+)"', contract_match.group(1)) == [
        "data_package_manifest",
        "dataset_contract",
        "relationship_contract",
        "crosswalk_manifest",
        "analysis_pack_request",
        "reconciliation_result",
        "prepared_evidence_manifest",
        "fdd_preparation_case",
        "fdd_calculation_result",
        "fdd_metric_receipt",
        "contingent_liability_register",
        "financial_issue_register",
    ]
    vera_mcp = json.loads((ROOT / "plugins" / "vera" / ".mcp.json").read_text())
    description = vera_mcp["mcpServers"]["financialAnalysisContracts"]["description"]
    assert "financial due-diligence" in description


def test_fdd_adversarial_contract_and_receipt_mutations_fail(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    result = execute_fdd_case(case)
    receipt = build_fdd_metric_receipt(case, result, "adjusted_ebitda")

    stale_case = deepcopy(case)
    stale_case["inputs"]["reported_ebitda"]["amount"] = "999"
    with pytest.raises(FDDContractError, match="digest is stale"):
        validate_fdd_case(stale_case)

    missing_package = deepcopy(case)
    del missing_package["contract_stack"]["package"]
    missing_package = _seal(missing_package)
    with pytest.raises(FDDContractError, match="contract_stack"):
        validate_fdd_case(missing_package)

    forged_result = deepcopy(result)
    forged_result["metrics"][0]["value"] = "999"
    forged_result = _seal(forged_result)
    with pytest.raises(FDDContractError, match="replay"):
        validate_fdd_calculation_result(forged_result, case=case)

    stale_receipt = deepcopy(receipt)
    stale_receipt["value"] = "999"
    stale_receipt = _seal(stale_receipt)
    with pytest.raises(FDDContractError, match="recomputed result"):
        validate_fdd_metric_receipt(stale_receipt)

    bad_evidence = _qoe_inputs()
    bad_evidence["adjustments"][0]["evidence_refs"] = ["artifact.unknown"]
    with pytest.raises(FDDContractError, match="unknown artifact"):
        _build_case(
            context,
            pack_id="quality_of_earnings",
            inputs=bad_evidence,
        )

    duplicate_effect = _qoe_inputs()
    duplicate_effect["adjustments"].append(
        {
            **duplicate_effect["adjustments"][0],
            "adjustment_id": "adjustment.two",
        }
    )
    with pytest.raises(FDDContractError, match="economic_effect_id"):
        _build_case(
            context,
            pack_id="quality_of_earnings",
            inputs=duplicate_effect,
        )


def test_registers_are_reviewed_evidence_not_completeness_or_deal_decisions(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    qoe_case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    qoe_result = execute_fdd_case(qoe_case)
    receipt = build_fdd_metric_receipt(
        qoe_case,
        qoe_result,
        "adjusted_ebitda",
    )
    common = {
        "case": qoe_case,
        "review": _review(),
        "reviewed_decisions": _decisions(),
    }
    contingencies = build_contingent_liability_register(
        register_id="register.contingencies.v1",
        **common,
        items=[
            {
                "contingency_id": "contingency.z",
                "economic_effect_id": "effect.contingency.z",
                "title": "Synthetic range exposure",
                "description": "Reviewed synthetic item.",
                "category_id": "category.tax",
                "amount_basis": {
                    "status": "range",
                    "amount": None,
                    "low": "10",
                    "high": "30",
                },
                "status_id": "status.open",
                "deal_treatment_id": "treatment.not_decided",
                "decision_ref": "decision.synthetic",
                "owner_ref": "owner.synthetic",
                "evidence_refs": [ARTIFACT_REF],
                "open_questions": ["Confirm final exposure."],
            },
            {
                "contingency_id": "contingency.a",
                "economic_effect_id": "effect.contingency.a",
                "title": "Synthetic unquantified exposure",
                "description": "Reviewed synthetic item.",
                "category_id": "category.legal",
                "amount_basis": {
                    "status": "unquantified",
                    "amount": None,
                    "low": None,
                    "high": None,
                },
                "status_id": "status.open",
                "deal_treatment_id": "treatment.not_decided",
                "decision_ref": "decision.synthetic",
                "owner_ref": "owner.synthetic",
                "evidence_refs": [ARTIFACT_REF],
                "open_questions": [],
            },
        ],
    )
    issues = build_financial_issue_register(
        register_id="register.issues.v1",
        **common,
        metric_receipts=[receipt],
        issues=[
            {
                "issue_id": "issue.one",
                "economic_effect_id": "effect.issue.one",
                "title": "Synthetic EBITDA issue",
                "description": "Reviewed evidence-linked issue.",
                "status_id": "status.open",
                "owner_ref": "owner.synthetic",
                "related_pack_refs": ["quality_of_earnings"],
                "related_metric_refs": [receipt["receipt_id"]],
                "impact": {
                    "status": "exact",
                    "amount": "-25",
                    "low": None,
                    "high": None,
                },
                "decision_refs": ["decision.synthetic"],
                "evidence_refs": [ARTIFACT_REF],
                "open_questions": ["Deal response remains undecided."],
            }
        ],
    )

    assert contingencies["schema_version"] == "vera.contingent_liability_register.v2"
    assert issues["schema_version"] == "vera.financial_issue_register.v2"
    assert [item["contingency_id"] for item in contingencies["items"]] == [
        "contingency.a",
        "contingency.z",
    ]
    assert contingencies["completeness"]["status"] == "not_assessed"
    assert issues["issues"][0]["impact"]["amount"] == "-25"
    assert issues["completeness"]["status"] == "not_assessed"
    assert issues["report_ready"] is False

    swapped_contingencies = deepcopy(contingencies)
    swapped_contingencies["package_ref"] = "package.fabricated.v1"
    swapped_contingencies = _seal(swapped_contingencies)
    with pytest.raises(FDDContractError, match="does not close"):
        validate_contingent_liability_register(swapped_contingencies)

    swapped_issues = deepcopy(issues)
    swapped_issues["source_artifacts"][0]["sha256"] = "0" * 64
    swapped_issues = _seal(swapped_issues)
    with pytest.raises(FDDContractError, match="does not close"):
        validate_financial_issue_register(swapped_issues)
