from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLAN_ROOT = ROOT / "plugins" / "sales-plan"
PLAN_SCRIPTS = PLAN_ROOT / "scripts"
ENGINE_SCRIPT = PLAN_SCRIPTS / "prepare_sales_plan_case.py"
RUNNER_SCRIPT = PLAN_SCRIPTS / "run_plan.py"
MCP_SCRIPT = PLAN_ROOT / "mcp" / "server.cjs"
VERA_MCP_RUNNER = ROOT / "plugins" / "vera" / "scripts" / "run_component_mcp.cjs"
FIXTURE_ROOT = PLAN_ROOT / "evals" / "synthetic"
if str(PLAN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLAN_SCRIPTS))


def _load_engine_module() -> ModuleType:
    if str(PLAN_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(PLAN_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "vera_sales_plan_preparation",
        ENGINE_SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_runner_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vera_sales_plan_runner",
        RUNNER_SCRIPT,
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
        pytest.skip("Node.js is required for the sales-plan MCP test.")
    return candidates[-1].as_posix()


def _copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "case"
    shutil.copytree(FIXTURE_ROOT, destination)
    return destination / "case.json"


def _load_case(case_path: Path) -> dict[str, Any]:
    return json.loads(case_path.read_text(encoding="utf-8"))


def _write_case(case_path: Path, case: dict[str, Any]) -> None:
    case_path.write_text(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rewrite_source_and_bind(
    case_path: Path,
    rows: list[dict[str, str]],
) -> None:
    source_path = case_path.parent / "actual_sales.csv"
    columns = list(rows[0])
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    case = _load_case(case_path)
    case["files"]["actual_sales"]["sha256"] = hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    _write_case(case_path, case)


def test_prepare_sales_plan_case_applies_china_growth_and_usd_decline(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    output_dir = tmp_path / "output"

    result = module.prepare_sales_plan_case(case_path, output_dir)

    assert result["status"] == "passed"
    assert result["report_ready"] is False
    summary = _read_csv(output_dir / "scenario_summary.csv")
    china_sales = next(
        row
        for row in summary
        if row["dimension_name"] == "country"
        and row["dimension_value"] == "China"
        and row["metric"] == "gross_sales_reporting"
    )
    assert china_sales["actual"] == "2004"
    assert china_sales["plan"] == "2056.104"
    assert china_sales["delta_pct_rounded_4dp"] == "2.6"


def test_prepare_sales_plan_case_writes_reviewable_assumption_ledger(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    output_dir = tmp_path / "output"

    module.prepare_sales_plan_case(case_path, output_dir)

    ledger = _read_csv(output_dir / "assumption_application_ledger.csv")
    assert len(ledger) == 4
    assert {row["assumption_id"] for row in ledger} == {
        "china-units-growth",
        "usd-eur-translation",
    }
    assert {row["status"] for row in ledger} == {"applied"}
    assert {row["application_mode"] for row in ledger} == {"single"}


def test_prepare_sales_plan_case_rejects_same_priority_overlap(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"].append(
        {
            "assumption_id": "china-units-conflict",
            "driver": "units_pct",
            "change_pct": "10",
            "scope": {"country": ["China"]},
            "effective_periods": ["2026-01", "2026-02"],
            "priority": 100,
            "rationale": "Synthetic conflicting reviewed assumption.",
        }
    )
    _write_case(case_path, case)

    result = module.prepare_sales_plan_case(case_path, tmp_path / "output")

    assert result["status"] == "failed"
    assert {error["code"] for error in result["errors"]} == {
        "ambiguous_same_priority_assumptions"
    }


def test_prepare_sales_plan_case_applies_explicit_priority(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"].append(
        {
            "assumption_id": "global-units-growth",
            "driver": "units_pct",
            "change_pct": "2",
            "scope": {},
            "effective_periods": ["2026-01", "2026-02"],
            "priority": 50,
            "rationale": "Synthetic global assumption below the China override.",
        }
    )
    _write_case(case_path, case)
    output_dir = tmp_path / "output"

    result = module.prepare_sales_plan_case(case_path, output_dir)

    assert result["status"] == "passed"
    summary = _read_csv(output_dir / "scenario_summary.csv")
    germany_sales = next(
        row
        for row in summary
        if row["dimension_name"] == "country"
        and row["dimension_value"] == "Germany"
        and row["metric"] == "gross_sales_reporting"
    )
    assert germany_sales["actual"] == "1700"
    assert germany_sales["plan"] == "1734"
    assert germany_sales["delta_pct_rounded_4dp"] == "2"
    ledger = _read_csv(output_dir / "assumption_application_ledger.csv")
    china_global_rows = [
        row
        for row in ledger
        if row["assumption_id"] == "global-units-growth"
        and row["source_row_id"].startswith("cn-")
    ]
    assert {row["status"] for row in china_global_rows} == {"overridden"}
    assert {row["overridden_by"] for row in china_global_rows} == {"china-units-growth"}
    assert {row["application_mode"] for row in china_global_rows} == {"overridden"}


def test_prepare_sales_plan_case_compounds_reviewed_same_driver_overlaps(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["preparation_recipe"]["same_driver_overlap_behavior"] = "compound"
    case["reviewed_assumptions"]["assumptions"].append(
        {
            "assumption_id": "global-units-growth",
            "driver": "units_pct",
            "change_pct": "10",
            "scope": {},
            "effective_periods": ["2026-01", "2026-02"],
            "priority": 100,
            "rationale": "Compound a global unit effect with the China effect.",
        }
    )
    _write_case(case_path, case)
    output_dir = tmp_path / "output"

    result = module.prepare_sales_plan_case(case_path, output_dir)

    assert result["status"] == "passed"
    plan_rows = _read_csv(output_dir / "sales_plan_scenario.csv")
    china_january = next(
        row
        for row in plan_rows
        if row["scenario"] == "PL" and row["source_row_id"] == "cn-bikes-2025-01"
    )
    assert china_january["units"] == "118.8"
    assert china_january["gross_sales_local"] == "1188"
    ledger = [
        row
        for row in _read_csv(output_dir / "assumption_application_ledger.csv")
        if row["source_row_id"] == "cn-bikes-2025-01" and row["driver"] == "units_pct"
    ]
    assert [row["assumption_id"] for row in ledger] == [
        "china-units-growth",
        "global-units-growth",
    ]
    assert [row["before_value"] for row in ledger] == ["100", "108"]
    assert [row["after_value"] for row in ledger] == ["108", "118.8"]
    assert {row["application_mode"] for row in ledger} == {"compound"}


def test_prepare_sales_plan_case_compounds_arbitrary_dimension_intersections(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["preparation_recipe"]["dimension_columns"] = [
        "market_code",
        "route_class",
    ]
    _write_case(case_path, case)
    _rewrite_source_and_bind(
        case_path,
        [
            {
                "source_row_id": "row-47",
                "period": "2025-01",
                "market_code": "Zone-47",
                "route_class": "Path-Wholesale",
                "transaction_currency": "GBP",
                "units": "10",
                "gross_sales_local": "100",
                "discount_local": "10",
                "cogs_local": "60",
                "fx_rate_to_reporting": "0.9",
            }
        ],
    )
    case = _load_case(case_path)
    case["preparation_recipe"]["same_driver_overlap_behavior"] = "compound"
    case["reviewed_assumptions"]["assumptions"] = [
        {
            "assumption_id": "market-growth",
            "driver": "gross_sales_pct",
            "change_pct": "30",
            "scope": {"market_code": ["Zone-47"]},
            "effective_periods": ["2026-01"],
            "priority": 100,
            "rationale": "Synthetic arbitrary market assumption.",
        },
        {
            "assumption_id": "route-decline",
            "driver": "gross_sales_pct",
            "change_pct": "-10",
            "scope": {"route_class": ["Path-Wholesale"]},
            "effective_periods": ["2026-01"],
            "priority": 100,
            "rationale": "Synthetic arbitrary route assumption.",
        },
        {
            "assumption_id": "gbp-rise",
            "driver": "fx_rate_pct",
            "change_pct": "20",
            "scope": {"transaction_currency": ["GBP"]},
            "effective_periods": ["2026-01"],
            "priority": 100,
            "rationale": "Synthetic arbitrary currency assumption.",
        },
    ]
    _write_case(case_path, case)
    output_dir = tmp_path / "output"

    result = module.prepare_sales_plan_case(case_path, output_dir)

    assert result["status"] == "passed"
    plan_row = next(
        row
        for row in _read_csv(output_dir / "sales_plan_scenario.csv")
        if row["scenario"] == "PL"
    )
    assert plan_row["gross_sales_local"] == "117"
    assert plan_row["fx_rate_to_reporting"] == "1.08"
    assert plan_row["gross_sales_reporting"] == "126.36"


def test_prepare_sales_plan_case_rejects_unmatched_scope(tmp_path: Path) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"][0]["scope"] = {"country": ["Atlantis"]}
    _write_case(case_path, case)

    result = module.prepare_sales_plan_case(case_path, tmp_path / "output")

    assert result["status"] == "failed"
    assert {error["code"] for error in result["errors"]} == {"unmatched_assumption"}


def test_prepare_sales_plan_case_rejects_direct_sales_and_volume_overlap(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"].append(
        {
            "assumption_id": "china-direct-sales",
            "driver": "gross_sales_pct",
            "change_pct": "4",
            "scope": {"country": ["China"]},
            "effective_periods": ["2026-01", "2026-02"],
            "priority": 100,
            "rationale": "Synthetic direct-sales overlap.",
        }
    )
    _write_case(case_path, case)

    result = module.prepare_sales_plan_case(case_path, tmp_path / "output")

    assert result["status"] == "failed"
    assert {error["code"] for error in result["errors"]} == {
        "direct_sales_and_driver_overlap"
    }


def test_prepare_sales_plan_case_rejects_stale_source_receipt(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    source_path = case_path.parent / "actual_sales.csv"
    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(module.ContractValidationError, match="sha256 is stale"):
        module.prepare_sales_plan_case(case_path, tmp_path / "output")


def test_prepare_sales_plan_case_rejects_non_unit_same_currency_fx(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    _rewrite_source_and_bind(
        case_path,
        [
            {
                "source_row_id": "same-currency-row",
                "period": "2025-01",
                "country": "Market-47",
                "product": "Route-Direct",
                "transaction_currency": "EUR",
                "units": "10",
                "gross_sales_local": "100",
                "discount_local": "10",
                "cogs_local": "60",
                "fx_rate_to_reporting": "0.8",
            }
        ],
    )
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"] = [
        {
            "assumption_id": "no-change",
            "driver": "gross_sales_pct",
            "change_pct": "0",
            "scope": {},
            "effective_periods": ["2026-01"],
            "priority": 100,
            "rationale": "Keep the scenario unchanged.",
        }
    ]
    _write_case(case_path, case)

    with pytest.raises(
        module.ContractValidationError,
        match="must equal 1 when transaction currency equals reporting currency",
    ):
        module.prepare_sales_plan_case(case_path, tmp_path / "output")


def test_prepare_sales_plan_case_rejects_fx_effect_on_reporting_currency(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    _rewrite_source_and_bind(
        case_path,
        [
            {
                "source_row_id": "same-currency-row",
                "period": "2025-01",
                "country": "Market-47",
                "product": "Route-Direct",
                "transaction_currency": "EUR",
                "units": "10",
                "gross_sales_local": "100",
                "discount_local": "10",
                "cogs_local": "60",
                "fx_rate_to_reporting": "1",
            }
        ],
    )
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"] = [
        {
            "assumption_id": "global-fx-rise",
            "driver": "fx_rate_pct",
            "change_pct": "10",
            "scope": {},
            "effective_periods": ["2026-01"],
            "priority": 100,
            "rationale": "Exercise the same-currency FX invariant.",
        }
    ]
    _write_case(case_path, case)

    result = module.prepare_sales_plan_case(case_path, tmp_path / "output")

    assert result["status"] == "failed"
    assert {error["code"] for error in result["errors"]} == {"same_currency_fx_changed"}


def test_prepare_sales_plan_case_rejects_units_effect_on_zero_units(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    _rewrite_source_and_bind(
        case_path,
        [
            {
                "source_row_id": "zero-unit-row",
                "period": "2025-01",
                "country": "Market-47",
                "product": "Route-Direct",
                "transaction_currency": "GBP",
                "units": "0",
                "gross_sales_local": "100",
                "discount_local": "10",
                "cogs_local": "60",
                "fx_rate_to_reporting": "0.9",
            }
        ],
    )
    case = _load_case(case_path)
    case["reviewed_assumptions"]["assumptions"] = [
        {
            "assumption_id": "unit-growth",
            "driver": "units_pct",
            "change_pct": "10",
            "scope": {},
            "effective_periods": ["2026-01"],
            "priority": 100,
            "rationale": "Exercise the positive-units invariant.",
        }
    ]
    _write_case(case_path, case)

    result = module.prepare_sales_plan_case(case_path, tmp_path / "output")

    assert result["status"] == "failed"
    assert {error["code"] for error in result["errors"]} == {
        "units_required_for_volume_or_price_driver"
    }


def test_prepare_sales_plan_case_preserves_sparse_observed_grains(
    tmp_path: Path,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    rows = [
        row
        for row in _read_csv(case_path.parent / "actual_sales.csv")
        if row["source_row_id"] != "de-bikes-2025-02"
    ]
    _rewrite_source_and_bind(case_path, rows)
    output_dir = tmp_path / "output"

    result = module.prepare_sales_plan_case(case_path, output_dir)

    assert result["status"] == "passed"
    assert result["source_profile"] == {
        "declared_grains": 2,
        "sparse_grains": 1,
        "missing_grain_periods": 1,
    }
    assert result["counts"]["source_rows"] == 3
    assert result["counts"]["scenario_rows"] == 6
    assert {warning["code"] for warning in result["warnings"]} == {
        "sparse_source_time_profile"
    }


@pytest.mark.parametrize(
    (
        "assumption_basis",
        "expected_discount",
        "expected_cogs",
        "expected_discount_value_name",
        "expected_cogs_value_name",
    ),
    [
        (
            "actual_amount",
            "45",
            "630",
            "discount_local",
            "cogs_local",
        ),
        (
            "sales_adjusted_amount",
            "48.6",
            "680.4",
            "discount_local_after_sales",
            "cogs_local_after_sales",
        ),
    ],
)
def test_prepare_sales_plan_case_applies_explicit_cost_bases(
    tmp_path: Path,
    assumption_basis: str,
    expected_discount: str,
    expected_cogs: str,
    expected_discount_value_name: str,
    expected_cogs_value_name: str,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["preparation_recipe"]["discount_assumption_basis"] = assumption_basis
    case["preparation_recipe"]["cogs_assumption_basis"] = assumption_basis
    case["reviewed_assumptions"]["assumptions"].extend(
        [
            {
                "assumption_id": "china-discount-change",
                "driver": "discount_pct",
                "change_pct": "-10",
                "scope": {"country": ["China"]},
                "effective_periods": ["2026-01", "2026-02"],
                "priority": 100,
                "rationale": "Apply the reviewed discount basis.",
            },
            {
                "assumption_id": "china-cogs-change",
                "driver": "cogs_pct",
                "change_pct": "5",
                "scope": {"country": ["China"]},
                "effective_periods": ["2026-01", "2026-02"],
                "priority": 100,
                "rationale": "Apply the reviewed COGS basis.",
            },
        ]
    )
    _write_case(case_path, case)
    output_dir = tmp_path / "output"

    result = module.prepare_sales_plan_case(case_path, output_dir)

    assert result["status"] == "passed"
    scenario = next(
        row
        for row in _read_csv(output_dir / "sales_plan_scenario.csv")
        if row["scenario"] == "PL" and row["source_row_id"] == "cn-bikes-2025-01"
    )
    assert scenario["discount_local"] == expected_discount
    assert scenario["cogs_local"] == expected_cogs
    ledger = _read_csv(output_dir / "assumption_application_ledger.csv")
    discount_row = next(
        row
        for row in ledger
        if row["assumption_id"] == "china-discount-change"
        and row["source_row_id"] == "cn-bikes-2025-01"
    )
    cogs_row = next(
        row
        for row in ledger
        if row["assumption_id"] == "china-cogs-change"
        and row["source_row_id"] == "cn-bikes-2025-01"
    )
    assert discount_row["driver_value_name"] == expected_discount_value_name
    assert cogs_row["driver_value_name"] == expected_cogs_value_name


def test_prepare_sales_plan_case_rejects_source_change_during_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    source_path = case_path.parent / "actual_sales.csv"
    original_read = module.read_exact_csv_snapshot_beneath

    def read_then_mutate(*args: Any, **kwargs: Any) -> Any:
        result = original_read(*args, **kwargs)
        source_path.write_text(
            source_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        module,
        "read_exact_csv_snapshot_beneath",
        read_then_mutate,
    )

    with pytest.raises(
        module.ContractValidationError,
        match="actual sales source changed during Plan execution",
    ):
        module.prepare_sales_plan_case(case_path, tmp_path / "output")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("same_driver_overlap_behavior", "guess"),
        ("discount_assumption_basis", "implicit"),
        ("cogs_assumption_basis", "implicit"),
    ],
)
def test_prepare_sales_plan_case_rejects_unsupported_reviewed_behavior(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    case = _load_case(case_path)
    case["preparation_recipe"][field] = value
    _write_case(case_path, case)

    with pytest.raises(
        module.ContractValidationError,
        match=f"preparation_recipe.{field} must be one of",
    ):
        module.prepare_sales_plan_case(case_path, tmp_path / "output")


def test_prepare_sales_plan_case_is_byte_deterministic(tmp_path: Path) -> None:
    module = _load_engine_module()
    case_path = _copy_fixture(tmp_path)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    module.prepare_sales_plan_case(case_path, first_dir)
    module.prepare_sales_plan_case(case_path, second_dir)

    first_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(first_dir.iterdir())
    }
    second_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(second_dir.iterdir())
    }
    assert first_hashes == second_hashes


def test_run_plan_writes_a_standalone_execution_receipt(tmp_path: Path) -> None:
    module = _load_runner_module()
    case_path = _copy_fixture(tmp_path)
    output_dir = tmp_path / "output"

    receipt = module.run_plan(case_path=case_path, output_dir=output_dir)

    assert receipt["schema_version"] == "vera.sales_plan_execution.v2"
    assert receipt["workflow"] == "sales-plan"
    assert receipt["recipe_id"] == "sales_plan_from_reviewed_actuals.v2"
    assert receipt["status"] == "passed"
    assert receipt["report_ready"] is False
    assert receipt["source_path"] == "actual_sales.csv"
    assert (
        receipt["source_sha256"]
        == hashlib.sha256(
            (case_path.parent / "actual_sales.csv").read_bytes()
        ).hexdigest()
    )
    assert {artifact["path"] for artifact in receipt["output_artifacts"]} == {
        "assumption_application_ledger.csv",
        "prepared_evidence_manifest.json",
        "reconciliation.json",
        "sales_plan_scenario.csv",
        "scenario_summary.csv",
    }
    written_receipt = json.loads(
        (output_dir / "plan_execution_receipt.json").read_text(encoding="utf-8")
    )
    assert written_receipt == receipt


def test_run_plan_canonicalizes_standard_macos_tempfile_paths() -> None:
    module = _load_runner_module()
    temp_root = Path(tempfile.mkdtemp(prefix="vera-plan-path-alias-"))
    try:
        case_path = _copy_fixture(temp_root)
        output_dir = temp_root / "output"

        receipt = module.run_plan(case_path=case_path, output_dir=output_dir)

        assert receipt["status"] == "passed"
        assert receipt["source_path"] == "actual_sales.csv"
    finally:
        shutil.rmtree(temp_root)


def test_sales_plan_mcp_describes_only_the_plan_workflow() -> None:
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
                "name": "describe_vera_sales_plan",
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
    assert responses[0]["result"]["serverInfo"] == {
        "name": "vera-sales-plan",
        "version": "0.1.2",
    }
    payload = responses[1]["result"]["structuredContent"]
    assert payload["workflow"] == "vera.sales_plan"
    assert payload["recipe_id"] == "sales_plan_from_reviewed_actuals.v2"
    assert payload["report_ready"] is False
    assert payload["artifacts"] == [
        "sales_plan_scenario.csv",
        "assumption_application_ledger.csv",
        "scenario_summary.csv",
        "reconciliation.json",
        "prepared_evidence_manifest.json",
        "plan_execution_receipt.json",
    ]


def test_sales_plan_mcp_routes_through_vera_component_launcher() -> None:
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
                "name": "describe_vera_sales_plan",
                "arguments": {},
            },
        },
    ]

    result = subprocess.run(
        [_node_binary(), str(VERA_MCP_RUNNER), "sales-plan"],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )

    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["result"]["serverInfo"]["name"] == "vera-sales-plan"
    assert (
        responses[1]["result"]["structuredContent"]["recipe_id"]
        == "sales_plan_from_reviewed_actuals.v2"
    )
