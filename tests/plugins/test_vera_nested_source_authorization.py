from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tests.plugins._financial_analysis_test_loader import (
    load_financial_analysis_scripts,
)

ROOT = Path(__file__).resolve().parents[2]
SALES_SCRIPTS = ROOT / "plugins" / "sales-plan" / "scripts"
FINANCIAL_SCRIPTS = ROOT / "plugins" / "financial-analysis" / "scripts"
FINANCIAL_MODULES = ROOT / "plugins" / "_shared" / "vendor" / "modules"
LEDGER_SCRIPT = ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py"

for _import_root in (SALES_SCRIPTS, FINANCIAL_SCRIPTS, FINANCIAL_MODULES):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from managed_case_inputs import declared_case_input_paths
from vera_financial_analysis import (
    build_data_package_manifest,
    build_dataset_contract,
    build_fdd_case,
    canonical_json_sha256,
)

FINANCIAL = load_financial_analysis_scripts(FINANCIAL_SCRIPTS)


def _load_module(name: str, path: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ledger() -> ModuleType:
    return _load_module("test_nested_source_client_ledger", LEDGER_SCRIPT)


def _sales_runner() -> ModuleType:
    return _load_module(
        "test_nested_source_sales_runner",
        SALES_SCRIPTS / "run_plan.py",
    )


def _copy_sales_fixture(destination: Path) -> tuple[Path, tuple[Path, ...]]:
    shutil.copytree(
        ROOT / "plugins" / "sales-plan" / "evals" / "synthetic", destination
    )
    case_path = destination / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    source_path = destination / case["files"]["actual_sales"]["path"]
    return case_path, (source_path,)


def _copy_financial_fixture(
    destination: Path,
    *,
    pack_id: str,
) -> tuple[Path, tuple[Path, ...]]:
    source_case = {
        "monthly_pnl": ROOT / "plugins/clara/evals/preparation/wd40_fy2025/case.json",
        "working_capital": ROOT
        / "plugins/clara/evals/preparation/wd40_fy2025_working_capital/case.json",
        "customer_concentration": ROOT
        / "plugins/clara/evals/preparation/udc_fy2025_customer_concentration/case.json",
    }[pack_id]
    shutil.copytree(source_case.parent, destination)
    case_path = destination / source_case.name
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
    return case_path, declared_case_input_paths(case_path, pack_id)


def _write_fdd_fixture(destination: Path) -> tuple[Path, tuple[Path, ...]]:
    destination.mkdir()
    source_path = destination / "source.txt"
    source_path.write_text("synthetic reviewed evidence\n", encoding="utf-8")
    source_bytes = source_path.read_bytes()
    artifact_ref = "artifact.source"
    dataset_ref = "dataset.source.v1"
    reporting_period = {"start": "2025-01-01", "end": "2025-12-31"}
    package = build_data_package_manifest(
        package_id="package.synthetic.v1",
        snapshot_id="package.synthetic.v1.snapshot",
        reporting_perimeter={
            "entity_refs": ["entity.synthetic"],
            "period_start": reporting_period["start"],
            "period_end": reporting_period["end"],
            "currency_refs": ["EUR"],
        },
        sensitivity="confidential",
        sources=[
            {
                "source_id": "source.synthetic",
                "artifact_ref": artifact_ref,
                "file_name": source_path.name,
                "locator": source_path.name,
                "byte_count": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "snapshot_id": "package.synthetic.v1.snapshot",
                "dataset_contract_ref": dataset_ref,
            }
        ],
    )
    dataset = build_dataset_contract(
        dataset_contract_id=dataset_ref,
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
                "unit": "EUR_units",
                "currency": "EUR",
                "aggregation": "sum",
                "period_role": "period_end",
            },
        ],
        period={
            "calendar": "gregorian",
            "grain": "month",
            "start": reporting_period["start"],
            "end": reporting_period["end"],
        },
        source_artifact_refs=[artifact_ref],
    )
    case = build_fdd_case(
        case_id="case.synthetic",
        scope_id="scope.synthetic",
        entity_refs=["entity.synthetic"],
        pack_id="quality_of_earnings",
        currency="EUR",
        unit="EUR_units",
        reporting_period=reporting_period,
        package=package,
        datasets=[dataset],
        request_id="request.quality_of_earnings.v1",
        review={
            "status": "reviewed",
            "reviewed_on": "2026-07-28",
            "reviewer_ref": "reviewer.synthetic",
            "basis": "Reviewed synthetic fixture.",
        },
        reviewed_decisions=[
            {
                "decision_ref": "decision.synthetic",
                "status": "reviewed",
                "reviewed_on": "2026-07-28",
                "reviewer_ref": "reviewer.synthetic",
                "basis": "Reviewed synthetic fixture.",
            }
        ],
        inputs={
            "reported_ebitda": {
                "amount": "1000",
                "evidence_refs": [artifact_ref],
            },
            "adjustments": [
                {
                    "adjustment_id": "adjustment.one",
                    "economic_effect_id": "effect.ebitda.one",
                    "description": "Reviewed adjustment.",
                    "category_id": "category.reviewed",
                    "period_start": reporting_period["start"],
                    "period_end": reporting_period["end"],
                    "ebitda_impact": "100",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "cash_effect": "not_assessed",
                    "evidence_refs": [artifact_ref],
                }
            ],
        },
    )
    stack = case["contract_stack"]
    content = {
        "schema_version": "vera.fdd_execution_bundle.v2",
        "package": stack["package"],
        "datasets": stack["datasets"],
        "relationships": stack["relationships"],
        "crosswalks": stack["crosswalks"],
        "request": stack["request"],
        "fdd_case": case,
    }
    bundle = {**content, "content_sha256": canonical_json_sha256(content)}
    case_path = destination / "case.json"
    case_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return case_path, (source_path,)


def _managed_run(
    tmp_path: Path,
    *,
    workflow_id: str,
    case_path: Path,
    nested_paths: tuple[Path, ...],
    select_nested: bool,
) -> SimpleNamespace:
    ledger = _ledger()
    client_root = tmp_path / "Customer"
    client_root.mkdir()
    client_id = "client_555555555555555555555555"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Nested sources")
    engagement_id = engagement["engagement_id"]
    seed = tmp_path / "seed.txt"
    seed.write_text("seed\n", encoding="utf-8")
    imported = ledger.import_document(
        client_root,
        client_id,
        engagement_id,
        seed,
        "source",
    )
    upstream = ledger.prepare_run(
        client_root,
        client_id,
        engagement_id,
        "client-file-preparation",
        "test-version",
        input_ids=[imported["receipt"]["input_id"]],
        new_run=True,
    )
    upstream = ledger.start_run(
        client_root,
        engagement_id,
        upstream["run"]["run_id"],
    )
    upstream_output = Path(upstream["output_dir"])
    artifacts = (("fixture.case", case_path),) + tuple(
        (f"fixture.source.{index}", path)
        for index, path in enumerate(nested_paths, start=1)
    )
    for _artifact_id, source in artifacts:
        shutil.copy2(source, upstream_output / source.name)
    finalized = ledger.finalize_run(
        client_root,
        engagement_id,
        upstream["run"]["run_id"],
        [
            {
                "artifact_id": artifact_id,
                "path": source.name,
                "purpose": "Managed nested-source authorization fixture.",
                "audience": "internal",
                "media_type": "application/octet-stream",
            }
            for artifact_id, source in artifacts
        ],
    )
    selected = artifacts if select_nested else artifacts[:1]
    downstream = ledger.prepare_run(
        client_root,
        client_id,
        engagement_id,
        workflow_id,
        "test-version",
        upstream_artifacts=[
            {
                "run_id": finalized["run"]["run_id"],
                "artifact_id": artifact_id,
                "role": "case" if artifact_id == "fixture.case" else "source",
            }
            for artifact_id, _source in selected
        ],
        new_run=True,
    )
    running = ledger.start_run(
        client_root,
        engagement_id,
        downstream["run"]["run_id"],
    )
    case_binding = next(
        item
        for item in running["context"]["input_bindings"]
        if item.get("upstream_artifact_id") == "fixture.case"
    )
    execution_case = Path(case_binding["path"])
    if not select_nested:
        for source in nested_paths:
            shutil.copy2(source, execution_case.parent / source.name)
    return SimpleNamespace(
        client_root=client_root,
        context_path=Path(running["context_path"]),
        output_dir=Path(running["output_dir"]),
        case_path=execution_case,
    )


def _renamed(run: SimpleNamespace, name: str) -> SimpleNamespace:
    renamed_root = run.client_root.with_name(name)
    run.client_root.rename(renamed_root)
    return SimpleNamespace(
        client_root=renamed_root,
        context_path=renamed_root / run.context_path.relative_to(run.client_root),
        output_dir=renamed_root / run.output_dir.relative_to(run.client_root),
        case_path=renamed_root / run.case_path.relative_to(run.client_root),
    )


def _assert_empty(path: Path) -> None:
    assert path.is_dir()
    assert list(path.iterdir()) == []


def test_sales_plan_rejects_unreceipted_declared_source_before_write(
    tmp_path: Path,
) -> None:
    case_path, nested_paths = _copy_sales_fixture(tmp_path / "fixture")
    run = _managed_run(
        tmp_path,
        workflow_id="sales-plan",
        case_path=case_path,
        nested_paths=nested_paths,
        select_nested=False,
    )

    return_code = _sales_runner().main(
        [
            "--case",
            str(run.case_path),
            "--output-dir",
            str(run.output_dir),
            "--client-engagement",
            str(run.context_path),
        ]
    )

    assert return_code == 2
    _assert_empty(run.output_dir)


def test_sales_plan_uses_exact_nested_source_after_customer_folder_rename(
    tmp_path: Path,
) -> None:
    case_path, nested_paths = _copy_sales_fixture(tmp_path / "fixture")
    run = _renamed(
        _managed_run(
            tmp_path,
            workflow_id="sales-plan",
            case_path=case_path,
            nested_paths=nested_paths,
            select_nested=True,
        ),
        "Renamed Sales Customer",
    )

    return_code = _sales_runner().main(
        [
            "--case",
            str(run.case_path),
            "--output-dir",
            str(run.output_dir),
            "--client-engagement",
            str(run.context_path),
        ]
    )

    assert return_code == 0
    assert (run.output_dir / "plan_execution_receipt.json").is_file()


@pytest.mark.parametrize(
    "pack_id",
    [
        "monthly_pnl",
        "working_capital",
        "customer_concentration",
        "quality_of_earnings",
    ],
)
def test_financial_analysis_rejects_unreceipted_nested_sources_before_write(
    tmp_path: Path,
    pack_id: str,
) -> None:
    if pack_id == "quality_of_earnings":
        case_path, nested_paths = _write_fdd_fixture(tmp_path / "fixture")
    else:
        case_path, nested_paths = _copy_financial_fixture(
            tmp_path / "fixture",
            pack_id=pack_id,
        )
    run = _managed_run(
        tmp_path,
        workflow_id="financial-analysis",
        case_path=case_path,
        nested_paths=nested_paths,
        select_nested=False,
    )

    return_code = FINANCIAL.pack_runner.main(
        [
            "--pack",
            pack_id,
            "--case",
            str(run.case_path),
            "--output-dir",
            str(run.output_dir),
            "--client-engagement",
            str(run.context_path),
        ]
    )

    assert return_code == 2
    _assert_empty(run.output_dir)


@pytest.mark.parametrize(
    "pack_id",
    [
        "monthly_pnl",
        "working_capital",
        "customer_concentration",
        "quality_of_earnings",
    ],
)
def test_financial_analysis_nested_sources_survive_customer_folder_rename(
    tmp_path: Path,
    pack_id: str,
) -> None:
    if pack_id == "quality_of_earnings":
        case_path, nested_paths = _write_fdd_fixture(tmp_path / "fixture")
    else:
        case_path, nested_paths = _copy_financial_fixture(
            tmp_path / "fixture",
            pack_id=pack_id,
        )
    run = _renamed(
        _managed_run(
            tmp_path,
            workflow_id="financial-analysis",
            case_path=case_path,
            nested_paths=nested_paths,
            select_nested=True,
        ),
        f"Renamed {pack_id} Customer",
    )

    return_code = FINANCIAL.pack_runner.main(
        [
            "--pack",
            pack_id,
            "--case",
            str(run.case_path),
            "--output-dir",
            str(run.output_dir),
            "--client-engagement",
            str(run.context_path),
        ]
    )

    assert return_code == 0
    assert (run.output_dir / "pack_execution_receipt.json").is_file()


@pytest.mark.parametrize(
    "pack_id",
    [
        "quality_of_earnings",
        "net_debt",
        "normalized_working_capital",
        "capex",
        "deal_bridges",
    ],
)
def test_all_fdd_pack_ids_authorize_their_package_source_locators(
    tmp_path: Path,
    pack_id: str,
) -> None:
    case_path, nested_paths = _write_fdd_fixture(tmp_path / "fixture")

    declared = declared_case_input_paths(case_path, pack_id)

    assert declared == nested_paths
