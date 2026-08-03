from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_ROOT = ROOT / "plugins" / "_shared" / "vendor" / "modules"
CASE_SCRIPT = (
    ROOT / "plugins" / "financial-analysis" / "scripts" / "validate_case_contracts.py"
)
FINANCIAL_SCRIPTS = ROOT / "plugins" / "financial-analysis" / "scripts"
PACK_SCRIPT = FINANCIAL_SCRIPTS / "run_pack.py"
MCP_SCRIPT = ROOT / "plugins" / "financial-analysis" / "mcp" / "server.cjs"
if str(ASSURANCE_ROOT) not in sys.path:
    sys.path.insert(0, str(ASSURANCE_ROOT))
if str(FINANCIAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FINANCIAL_SCRIPTS))

from vera_financial_analysis import (
    REGISTERED_ANALYSIS_PACK_RECIPES,
    REGISTERED_ANALYSIS_PACKS,
    FinancialAnalysisContractError,
    build_analysis_pack_request,
    build_crosswalk_manifest,
    build_data_package_manifest,
    build_dataset_contract,
    build_prepared_evidence_manifest,
    build_reconciliation_result,
    build_relationship_contract,
    canonical_json_sha256,
    validate_prepared_evidence_manifest,
)


def _load_case_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vera_financial_analysis_case_validator",
        CASE_SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_pack_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vera_financial_analysis_pack_runner",
        PACK_SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _node_binary() -> str:
    node_binary = shutil.which("node")
    if node_binary is not None:
        return node_binary
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("Node.js is required for the financial-analysis MCP test.")
    return candidates[-1].as_posix()


def test_financial_analysis_mcp_describes_all_registered_packs() -> None:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "describe_vera_financial_analysis",
                "arguments": {},
            },
        },
    ]

    result = subprocess.run(
        [_node_binary(), str(MCP_SCRIPT), "--stdio"],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )

    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["result"]["serverInfo"]["version"] == "0.2.4"
    assert responses[1]["result"]["structuredContent"]["registered_packs"] == [
        "monthly_pnl",
        "working_capital",
        "customer_concentration",
        "quality_of_earnings",
        "net_debt",
        "normalized_working_capital",
        "capex",
        "deal_bridges",
    ]


def _field(
    name: str,
    *,
    concept_id: str,
    data_type: str = "text",
    unit: str = "identifier",
    currency: str | None = None,
    aggregation: str = "none",
) -> dict[str, Any]:
    return {
        "name": name,
        "concept_id": concept_id,
        "data_type": data_type,
        "nullable": False,
        "unit": unit,
        "currency": currency,
        "aggregation": aggregation,
        "period_role": "none",
    }


def _vera_case(
    source_case_path: Path,
    destination: Path,
    *,
    pack_id: str,
) -> Path:
    shutil.copytree(source_case_path.parent, destination)
    case_path = destination / source_case_path.name
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["schema_version"] = {
        "monthly_pnl": "vera.monthly_pnl_preparation_case.v1",
        "working_capital": "vera.working_capital_preparation_case.v1",
        "customer_concentration": "vera.customer_concentration_preparation_case.v1",
    }[pack_id]
    if pack_id == "working_capital":
        policy_receipt = case["files"]["reviewed_working_capital_policy"]
        policy_path = destination / policy_receipt["path"]
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["schema_version"] = "vera.reviewed_working_capital_policy.v1"
        policy_bytes = (json.dumps(policy, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        policy_path.write_bytes(policy_bytes)
        policy_receipt["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
    case_path.write_text(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return case_path


def _retarget_customer_concentration_case(case_path: Path) -> None:
    """Rewrite the benchmark as a shorter case with different fiscal years."""

    case = json.loads(case_path.read_text(encoding="utf-8"))
    year_map = {"2025": "2027", "2024": "2026"}
    available_ar_source_years = ("2025",)

    facts_path = case_path.parent / case["files"]["exact_extracted_facts"]["path"]
    with facts_path.open("r", encoding="utf-8", newline="") as handle:
        fact_rows = [
            row for row in csv.DictReader(handle) if row["fiscal_year"] in year_map
        ]
    for row in fact_rows:
        source_year = row["fiscal_year"]
        target_year = year_map[source_year]
        row["fiscal_year"] = target_year
        row["fact_id"] = row["fact_id"].replace(
            f"_{source_year}_", f"_{target_year}_", 1
        )
    with facts_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fact_rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(fact_rows)

    control_facts_path = case_path.parent / case["files"]["exact_control_facts"]["path"]
    with control_facts_path.open("r", encoding="utf-8", newline="") as handle:
        source_control_rows = list(csv.DictReader(handle))
    control_rows = []
    for row in source_control_rows:
        source_year = row["fiscal_year"]
        if source_year not in year_map:
            continue
        if (
            row["metric_id"] == "total_accounts_receivable"
            and source_year not in available_ar_source_years
        ):
            continue
        target_year = year_map[source_year]
        row["fiscal_year"] = target_year
        row["control_id"] = row["control_id"].replace(
            f"_{source_year}_", f"_{target_year}_", 1
        )
        control_rows.append(row)
    with control_facts_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(control_rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(control_rows)

    case["preparation_recipe"]["fiscal_years"] = list(year_map.values())
    case["facts_contract"]["exact_row_count"] = len(fact_rows)
    case["control_facts_contract"]["exact_row_count"] = len(control_rows)
    case["reviewed_boundary"]["accounts_receivable_coverage_unavailable_years"] = [
        "2026"
    ]
    available_year_metrics = {
        "total_accounts_receivable",
        "disclosed_accounts_receivable_subtotal",
        "accounts_receivable_coverage_percent",
    }
    for metric_id, source_values in case["controls"].items():
        source_years = (
            available_ar_source_years
            if metric_id in available_year_metrics
            else tuple(year_map)
        )
        case["controls"][metric_id] = {
            year_map[source_year]: source_values[source_year]
            for source_year in source_years
        }
    case["files"]["exact_extracted_facts"]["sha256"] = hashlib.sha256(
        facts_path.read_bytes()
    ).hexdigest()
    case["files"]["exact_control_facts"]["sha256"] = hashlib.sha256(
        control_facts_path.read_bytes()
    ).hexdigest()
    case_path.write_text(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _case_contracts(pack_id: str = "monthly_pnl") -> dict[str, Any]:
    recipe_version = next(iter(REGISTERED_ANALYSIS_PACK_RECIPES[pack_id]))
    source_dataset = build_dataset_contract(
        dataset_contract_id="dataset.source.v1",
        dataset_id="source",
        version="v1",
        grain="one row per customer-period",
        keys=["customer_id"],
        fields=[
            _field("customer_id", concept_id="customer.identity"),
            _field(
                "amount",
                concept_id="revenue.amount",
                data_type="decimal",
                unit="currency",
                currency="EUR",
                aggregation="sum",
            ),
        ],
        period={
            "calendar": "gregorian",
            "grain": "month",
            "start": "2025-01-01",
            "end": "2025-12-31",
        },
        source_artifact_refs=["artifact.source"],
    )
    target_dataset = build_dataset_contract(
        dataset_contract_id="dataset.target.v1",
        dataset_id="target",
        version="v1",
        grain="one row per parent",
        keys=["parent_id"],
        fields=[_field("parent_id", concept_id="parent.identity")],
        period={
            "calendar": "gregorian",
            "grain": "month",
            "start": "2025-01-01",
            "end": "2025-12-31",
        },
        source_artifact_refs=["artifact.target"],
    )
    package = build_data_package_manifest(
        package_id="package.case.v1",
        snapshot_id="snapshot.v1",
        reporting_perimeter={
            "entity_refs": ["entity.case"],
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "currency_refs": ["EUR"],
        },
        sensitivity="confidential",
        sources=[
            {
                "source_id": "source.data",
                "artifact_ref": "artifact.source",
                "file_name": "source.csv",
                "locator": "rows",
                "byte_count": 101,
                "sha256": "a" * 64,
                "snapshot_id": "snapshot.v1",
                "dataset_contract_ref": "dataset.source.v1",
            },
            {
                "source_id": "target.data",
                "artifact_ref": "artifact.target",
                "file_name": "target.csv",
                "locator": "rows",
                "byte_count": 102,
                "sha256": "b" * 64,
                "snapshot_id": "snapshot.v1",
                "dataset_contract_ref": "dataset.target.v1",
            },
            {
                "source_id": "crosswalk.data",
                "artifact_ref": "artifact.crosswalk",
                "file_name": "crosswalk.csv",
                "locator": "rows",
                "byte_count": 103,
                "sha256": "c" * 64,
                "snapshot_id": "snapshot.v1",
                "dataset_contract_ref": "dataset.source.v1",
            },
        ],
    )
    crosswalk = build_crosswalk_manifest(
        crosswalk_id="crosswalk.customer_parent.v1",
        version="v1",
        artifact_ref="artifact.crosswalk",
        artifact_sha256="c" * 64,
        byte_count=103,
        source_dataset_ref="dataset.source.v1",
        target_dataset_ref="dataset.target.v1",
        source_key_fields=["customer_id"],
        target_key_fields=["parent_id"],
        mapping_row_count=5,
        duplicate_source_policy="fail",
        unmatched_source_policy="qualify",
    )
    relationship = build_relationship_contract(
        relationship_id="relationship.customer_parent.v1",
        version="v1",
        left_dataset_ref="dataset.source.v1",
        right_dataset_ref="dataset.target.v1",
        left_keys=["customer_id"],
        right_keys=["parent_id"],
        cardinality="many_to_many",
        join_type="left",
        unmatched_policy="qualify",
        null_policy="fail",
        duplicate_policy="fail",
        period_alignment="same_period",
        crosswalk_ref="crosswalk.customer_parent.v1",
    )
    parameters = {"currency": "EUR", "period_end": "2025-12-31"}
    request = build_analysis_pack_request(
        request_id="request.case.v1",
        pack_id=pack_id,
        recipe_version=recipe_version,
        dataset_refs=["dataset.source.v1", "dataset.target.v1"],
        relationship_refs=["relationship.customer_parent.v1"],
        crosswalk_refs=["crosswalk.customer_parent.v1"],
        parameters=parameters,
        requested_outputs=["prepared_table"],
    )
    reconciliation = build_reconciliation_result(
        reconciliation_id="reconciliation.case.v1",
        request_ref="request.case.v1",
        status="passed",
        checks=[
            {
                "check_id": "check.total",
                "required": True,
                "status": "passed",
                "expected": "10",
                "actual": "10",
                "difference": "0",
                "tolerance": "0",
                "evidence_refs": ["dataset.source.v1"],
                "detail": "Prepared total equals source total.",
            }
        ],
    )
    outputs = [
        {
            "artifact_ref": "artifact.prepared",
            "role": "prepared_table",
            "row_count": 5,
            "byte_count": 104,
            "sha256": "d" * 64,
        }
    ]
    prepared = build_prepared_evidence_manifest(
        manifest_id="prepared.case.v1",
        request_ref="request.case.v1",
        package_ref="package.case.v1",
        dataset_contract_refs=["dataset.source.v1", "dataset.target.v1"],
        relationship_contract_refs=["relationship.customer_parent.v1"],
        crosswalk_refs=["crosswalk.customer_parent.v1"],
        input_artifact_refs=[
            "artifact.crosswalk",
            "artifact.source",
            "artifact.target",
        ],
        recipe={
            "pack_id": pack_id,
            "version": recipe_version,
            "implementation_refs": ["financial_analysis.pack.v1"],
            "parameters_sha256": canonical_json_sha256(parameters),
        },
        reconciliation_ref="reconciliation.case.v1",
        preparation_status="passed",
        output_artifacts=outputs,
        replay={
            "status": "passed",
            "output_set_sha256": canonical_json_sha256(outputs),
        },
    )
    return {
        "package": package,
        "datasets": [source_dataset, target_dataset],
        "relationships": [relationship],
        "crosswalks": [crosswalk],
        "request": request,
        "reconciliation": reconciliation,
        "prepared_manifest": prepared,
    }


@pytest.mark.parametrize("pack_id", sorted(REGISTERED_ANALYSIS_PACKS))
def test_validate_case_contracts_accepts_each_registered_pack(pack_id: str) -> None:
    module = _load_case_module()

    audit = module.validate_case_contracts(**_case_contracts(pack_id))

    assert audit["status"] == "passed"
    assert audit["pack_id"] == pack_id
    assert audit["report_ready"] is False
    assert len(audit["content_sha256"]) == 64


def test_many_to_many_relationship_requires_reviewed_crosswalk() -> None:
    with pytest.raises(
        FinancialAnalysisContractError,
        match="require an explicit crosswalk_ref",
    ):
        build_relationship_contract(
            relationship_id="relationship.invalid.v1",
            version="v1",
            left_dataset_ref="dataset.source.v1",
            right_dataset_ref="dataset.target.v1",
            left_keys=["customer_id"],
            right_keys=["parent_id"],
            cardinality="many_to_many",
            join_type="left",
            unmatched_policy="qualify",
            null_policy="fail",
            duplicate_policy="fail",
            period_alignment="same_period",
        )


def test_analysis_request_rejects_unregistered_calculation_code() -> None:
    with pytest.raises(
        FinancialAnalysisContractError,
        match="analysis pack is not registered",
    ):
        build_analysis_pack_request(
            request_id="request.invalid.v1",
            pack_id="generated_python",
            recipe_version="v1",
            dataset_refs=["dataset.source.v1"],
            parameters={},
            requested_outputs=["prepared_table"],
        )


def test_analysis_request_rejects_unregistered_recipe_version() -> None:
    with pytest.raises(
        FinancialAnalysisContractError,
        match="recipe version is not registered",
    ):
        build_analysis_pack_request(
            request_id="request.invalid.v1",
            pack_id="monthly_pnl",
            recipe_version="generated.v99",
            dataset_refs=["dataset.source.v1"],
            parameters={},
            requested_outputs=["prepared_table"],
        )


def test_reconciliation_rejects_stale_exact_difference() -> None:
    with pytest.raises(
        FinancialAnalysisContractError,
        match="difference is stale",
    ):
        build_reconciliation_result(
            reconciliation_id="reconciliation.invalid.v1",
            request_ref="request.case.v1",
            status="passed",
            checks=[
                {
                    "check_id": "check.total",
                    "required": True,
                    "status": "passed",
                    "expected": "10",
                    "actual": "11",
                    "difference": "0",
                    "tolerance": "1",
                    "evidence_refs": ["dataset.source.v1"],
                    "detail": "Invalid stale arithmetic.",
                }
            ],
        )


def test_prepared_evidence_cannot_claim_report_readiness() -> None:
    prepared = dict(_case_contracts()["prepared_manifest"])
    prepared["report_ready"] = True
    content = {key: value for key, value in prepared.items() if key != "content_sha256"}
    prepared["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(
        FinancialAnalysisContractError,
        match="cannot establish report readiness",
    ):
        validate_prepared_evidence_manifest(prepared)


def test_prepared_evidence_rejects_noncanonical_output_order() -> None:
    prepared = deepcopy(_case_contracts()["prepared_manifest"])
    prepared["output_artifacts"].append(
        {
            "artifact_ref": "artifact.z",
            "role": "reconciliation",
            "row_count": 1,
            "byte_count": 105,
            "sha256": "e" * 64,
        }
    )
    prepared["output_artifacts"].reverse()
    prepared["replay"]["output_set_sha256"] = canonical_json_sha256(
        prepared["output_artifacts"]
    )
    content = {key: value for key, value in prepared.items() if key != "content_sha256"}
    prepared["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(
        FinancialAnalysisContractError,
        match="prepared evidence manifest is not canonical",
    ):
        validate_prepared_evidence_manifest(prepared)


def test_prepared_evidence_allows_multiple_artifacts_for_one_output_role() -> None:
    prepared = deepcopy(_case_contracts()["prepared_manifest"])
    prepared["output_artifacts"].append(
        {
            "artifact_ref": "artifact.z",
            "role": "prepared_table",
            "row_count": 1,
            "byte_count": 105,
            "sha256": "e" * 64,
        }
    )
    prepared["replay"]["output_set_sha256"] = canonical_json_sha256(
        prepared["output_artifacts"]
    )
    content = {key: value for key, value in prepared.items() if key != "content_sha256"}
    prepared["content_sha256"] = canonical_json_sha256(content)

    validated = validate_prepared_evidence_manifest(prepared)

    assert [item["artifact_ref"] for item in validated["output_artifacts"]] == [
        "artifact.prepared",
        "artifact.z",
    ]


def test_case_validator_rejects_crosswalk_receipt_outside_package() -> None:
    module = _load_case_module()
    contracts = _case_contracts()
    crosswalk = dict(contracts["crosswalks"][0])
    crosswalk["artifact_sha256"] = "e" * 64
    content = {
        key: value for key, value in crosswalk.items() if key != "content_sha256"
    }
    crosswalk["content_sha256"] = canonical_json_sha256(content)
    contracts["crosswalks"] = [crosswalk]

    with pytest.raises(
        module.FinancialAnalysisCaseError,
        match="crosswalk .* source digest does not close",
    ):
        module.validate_case_contracts(**contracts)


def test_cli_writes_deterministic_contract_audit(tmp_path: Path) -> None:
    module = _load_case_module()
    contracts = _case_contracts("working_capital")
    source_arguments: list[tuple[str, Path]] = []
    single_paths = {
        "package": "--package",
        "request": "--request",
        "reconciliation": "--reconciliation",
        "prepared_manifest": "--prepared-manifest",
    }
    for key, flag in single_paths.items():
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps(contracts[key]), encoding="utf-8")
        source_arguments.append((flag, path))
    for key, flag in (
        ("datasets", "--dataset"),
        ("relationships", "--relationship"),
        ("crosswalks", "--crosswalk"),
    ):
        for index, value in enumerate(contracts[key]):
            path = tmp_path / f"{key}-{index}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            source_arguments.append((flag, path))

    ledger_path = ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py"
    spec = importlib.util.spec_from_file_location(
        "financial_analysis_test_client_ledger",
        ledger_path,
    )
    assert spec and spec.loader
    ledger = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ledger
    spec.loader.exec_module(ledger)
    client_root = tmp_path / "Studio" / "Financial Client"
    client_root.mkdir(parents=True)
    client_id = "client_222222222222222222222222"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Financial review")
    imported = [
        ledger.import_document(
            client_root,
            client_id,
            engagement["engagement_id"],
            source,
            "source",
        )
        for _, source in source_arguments
    ]
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "financial-analysis",
        "test-version",
        input_ids=[item["receipt"]["input_id"] for item in imported],
    )
    running = ledger.start_run(
        client_root,
        engagement["engagement_id"],
        prepared["run"]["run_id"],
    )
    execution_by_name = {
        Path(item["path"]).name: Path(item["path"])
        for item in running["context"]["input_bindings"]
    }
    arguments: list[str] = []
    for flag, source in source_arguments:
        arguments.extend([flag, str(execution_by_name[source.name])])
    output = Path(running["output_dir"]) / "financial_analysis_contract_audit.json"
    arguments.extend(
        [
            "--output",
            str(output),
            "--client-engagement",
            str(running["context_path"]),
        ]
    )

    return_code = module.main(arguments)

    assert return_code == 0
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["pack_id"] == "working_capital"
    assert audit["counts"]["datasets"] == 2
    assert audit["report_ready"] is False


@pytest.mark.parametrize(
    ("pack_id", "case_path", "manifest_schema", "minimum_outputs"),
    [
        (
            "monthly_pnl",
            ROOT / "plugins/clara/evals/preparation/wd40_fy2025/case.json",
            "vera.monthly_pnl_evidence_manifest.v1",
            4,
        ),
        (
            "working_capital",
            ROOT
            / "plugins/clara/evals/preparation/wd40_fy2025_working_capital/case.json",
            "vera.working_capital_evidence_manifest.v1",
            7,
        ),
        (
            "customer_concentration",
            ROOT
            / "plugins/clara/evals/preparation/udc_fy2025_customer_concentration/case.json",
            "vera.customer_concentration_evidence_manifest.v1",
            4,
        ),
    ],
)
def test_registered_pack_engines_run_under_vera_and_are_byte_deterministic(
    tmp_path: Path,
    pack_id: str,
    case_path: Path,
    manifest_schema: str,
    minimum_outputs: int,
) -> None:
    module = _load_pack_module()
    case_path = _vera_case(
        case_path,
        tmp_path / "case",
        pack_id=pack_id,
    )
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    first = module.run_pack(
        pack_id=pack_id,
        case_path=case_path,
        output_dir=first_output,
    )
    second = module.run_pack(
        pack_id=pack_id,
        case_path=case_path,
        output_dir=second_output,
    )

    assert set(module.PACKS) == set(REGISTERED_ANALYSIS_PACKS)
    assert module.PACKS[pack_id].recipe_id in REGISTERED_ANALYSIS_PACK_RECIPES[pack_id]
    assert first == second
    assert first["status"] == "passed"
    assert first["report_ready"] is False
    assert len(first["output_artifacts"]) >= minimum_outputs
    manifest = json.loads(
        (first_output / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == manifest_schema
    assert manifest["report_ready"] is False


def test_customer_concentration_uses_case_declared_fiscal_years(
    tmp_path: Path,
) -> None:
    module = _load_pack_module()
    source_case_path = (
        ROOT
        / "plugins/clara/evals/preparation/udc_fy2025_customer_concentration/case.json"
    )
    case_path = _vera_case(
        source_case_path,
        tmp_path / "case",
        pack_id="customer_concentration",
    )
    _retarget_customer_concentration_case(case_path)
    output_dir = tmp_path / "prepared"

    result = module.run_pack(
        pack_id="customer_concentration",
        case_path=case_path,
        output_dir=output_dir,
    )

    assert result["status"] == "passed"
    reconciliation = json.loads(
        (output_dir / "reconciliation.json").read_text(encoding="utf-8")
    )
    assert reconciliation["counts"] == {
        "fact_rows": 12,
        "control_fact_rows": 3,
        "unique_fact_ids": 12,
        "unique_natural_keys": 12,
        "unique_control_ids": 3,
        "unique_control_natural_keys": 3,
        "summary_results": 10,
        "exception_rows": 0,
        "errors": 0,
    }
    assert reconciliation["availability_results"] == [
        {
            "summary_id": "udc_2026_accounts_receivable_coverage_percent",
            "fiscal_year": "2026",
            "metric_id": "accounts_receivable_coverage_percent",
            "status": "unavailable",
            "reason": (
                "The frozen source-control set contains no 2026 total "
                "accounts-receivable denominator."
            ),
        }
    ]
    with (output_dir / "customer_concentration_summary.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        summary_rows = list(csv.DictReader(handle))
    assert {row["fiscal_year"] for row in summary_rows} == {"2027", "2026"}
    assert {row["fiscal_year"] for row in summary_rows}.isdisjoint(
        {"2025", "2024", "2023"}
    )


def test_pack_runner_rejects_unregistered_pack_before_execution(tmp_path: Path) -> None:
    module = _load_pack_module()

    with pytest.raises(module.PackRunError, match="unregistered"):
        module.run_pack(
            pack_id="generated_code",
            case_path=tmp_path / "missing.json",
            output_dir=tmp_path / "output",
        )
