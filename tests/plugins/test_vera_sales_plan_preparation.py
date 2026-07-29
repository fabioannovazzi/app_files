from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_ROOT = ROOT / "plugins" / "_shared" / "vendor" / "modules"
FINANCIAL_SCRIPTS = ROOT / "plugins" / "financial-analysis" / "scripts"
ENGINE_SCRIPT = FINANCIAL_SCRIPTS / "prepare_sales_plan_case.py"
FIXTURE_ROOT = (
    ROOT / "plugins" / "financial-analysis" / "evals" / "sales_plan_synthetic"
)
if str(ASSURANCE_ROOT) not in sys.path:
    sys.path.insert(0, str(ASSURANCE_ROOT))
if str(FINANCIAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FINANCIAL_SCRIPTS))


def _load_engine_module() -> ModuleType:
    if str(FINANCIAL_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(FINANCIAL_SCRIPTS))
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
