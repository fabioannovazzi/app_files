from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins" / "clara" / "scripts" / "validate_public_truth_benchmark.py"
CASE_ROOT = ROOT / "plugins" / "clara" / "evals" / "public_truth" / "fastenal_q1_2025"
BENCHMARK = CASE_ROOT / "benchmark.json"
EXPECTED = CASE_ROOT / "expected_prepared_observations.csv"
EXPECTED_BENCHMARK_SHA256 = (
    "88b859f1e43a2ee6883bb9c6c7b9e61bcae26108de9db7c8deabf77d97dd22fc"
)
EXPECTED_OBSERVATIONS_SHA256 = (
    "bf27e23960f1050394584f865a8fd59a7f7db1f9cabfa3345be923094fbc6eac"
)
EXPECTED_REPORT_SHA256 = (
    "56d95fbe302c72b9258476b9965e71265c8eae0d9f299458c70d00221e88bed4"
)


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_public_truth_benchmark_test",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_candidate_rows() -> list[dict[str, str]]:
    with EXPECTED.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_candidate(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _assertion(report: dict[str, Any], assertion_id: str) -> dict[str, Any]:
    return next(
        item
        for item in report["assertion_results"]
        if item["assertion_id"] == assertion_id
    )


def test_fastenal_public_truth_fixture_is_pinned_and_passes() -> None:
    module = _load_module()

    report = module.validate_public_truth_case(BENCHMARK, EXPECTED)

    assert hashlib.sha256(BENCHMARK.read_bytes()).hexdigest() == (
        EXPECTED_BENCHMARK_SHA256
    )
    assert hashlib.sha256(EXPECTED.read_bytes()).hexdigest() == (
        EXPECTED_OBSERVATIONS_SHA256
    )
    assert report["status"] == "passed"
    assert report["benchmark_passed"] is True
    assert report["downstream_readiness"] == {
        "status": "not_assessed",
        "reason": (
            "Render compatibility and evidence sealing are outside this "
            "public-truth benchmark."
        ),
    }
    assert report["counts"] == {
        "expected": 13,
        "candidate": 13,
        "matched": 13,
        "missing": 0,
        "unexpected": 0,
        "mismatched": 0,
        "duplicates": 0,
        "assertions_passed": 5,
        "assertions_failed": 0,
        "abstention_failures": 0,
        "errors": 0,
        "warnings": 0,
    }
    assert report["abstention_result"] == {
        "status": "passed",
        "metric_ids": [
            "cost_of_sales",
            "gross_profit",
            "selling_general_administrative",
            "operating_income",
            "interest_income",
            "interest_expense",
            "pretax_income",
            "income_tax",
            "net_income",
        ],
        "offending_observation_ids": [],
    }
    rounded_sum = _assertion(report, "monthly_net_sales_to_q1")
    assert rounded_sum == {
        "assertion_id": "monthly_net_sales_to_q1",
        "kind": "rounded_sum",
        "status": "passed",
        "source_total": "1959.429",
        "target_value": "1959.4",
        "difference": "0.029",
        "tolerance": "0.0515",
        "unit": "USD_million",
    }
    assert report["boundary"]["monthly_reported_metric_ids"] == ["net_sales"]
    assert set(report["boundary"]["monthly_not_disclosed_metric_ids"]) == {
        "cost_of_sales",
        "gross_profit",
        "selling_general_administrative",
        "operating_income",
        "interest_income",
        "interest_expense",
        "pretax_income",
        "income_tax",
        "net_income",
    }
    canonical_report = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert hashlib.sha256(canonical_report).hexdigest() == EXPECTED_REPORT_SHA256


def test_public_truth_validator_rejects_missing_month(tmp_path: Path) -> None:
    module = _load_module()
    rows = [
        row
        for row in _read_candidate_rows()
        if row["observation_id"] != "fastenal_2025_02_net_sales"
    ]
    candidate = tmp_path / "missing_february.csv"
    _write_candidate(candidate, rows)

    report = module.validate_public_truth_case(BENCHMARK, candidate)

    assert report["status"] == "failed"
    assert report["benchmark_passed"] is False
    assert report["counts"]["missing"] == 1
    assert _assertion(report, "monthly_net_sales_to_q1") == {
        "assertion_id": "monthly_net_sales_to_q1",
        "kind": "rounded_sum",
        "status": "failed",
        "reason": "missing_observations",
        "missing_observation_ids": ["fastenal_2025_02_net_sales"],
    }


def test_public_truth_validator_rejects_invented_monthly_expense(
    tmp_path: Path,
) -> None:
    module = _load_module()
    rows = _read_candidate_rows()
    rows.append(
        {
            "observation_id": "invented_2025_01_cost_of_sales",
            "metric_id": "cost_of_sales",
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
            "period_grain": "month",
            "value": "350.0",
            "unit": "USD_million",
            "reported_increment": "0.1",
            "source_id": "fastenal_q1_2025_10q",
            "source_locator": "No monthly source; deliberately invented",
        }
    )
    candidate = tmp_path / "invented_monthly_cost.csv"
    _write_candidate(candidate, rows)

    report = module.validate_public_truth_case(BENCHMARK, candidate)

    assert report["status"] == "failed"
    assert report["benchmark_passed"] is False
    assert report["counts"]["unexpected"] == 1
    assert report["counts"]["abstention_failures"] == 1
    assert report["abstention_result"]["status"] == "failed"
    assert report["abstention_result"]["offending_observation_ids"] == [
        "invented_2025_01_cost_of_sales"
    ]
    assert report["fact_results"][-1] == {
        "observation_id": "invented_2025_01_cost_of_sales",
        "status": "unexpected",
    }


def test_public_truth_validator_rejects_value_outside_rounding_interval(
    tmp_path: Path,
) -> None:
    module = _load_module()
    rows = _read_candidate_rows()
    january = next(
        row for row in rows if row["observation_id"] == "fastenal_2025_01_net_sales"
    )
    january["value"] = "652.300"
    candidate = tmp_path / "outside_rounding_interval.csv"
    _write_candidate(candidate, rows)

    report = module.validate_public_truth_case(BENCHMARK, candidate)

    assert report["status"] == "failed"
    assert report["counts"]["mismatched"] == 1
    rounded_sum = _assertion(report, "monthly_net_sales_to_q1")
    assert rounded_sum["status"] == "failed"
    assert rounded_sum["difference"] == "0.086"
    assert rounded_sum["tolerance"] == "0.0515"


def test_public_truth_validator_rejects_broken_statement_identity(
    tmp_path: Path,
) -> None:
    module = _load_module()
    rows = _read_candidate_rows()
    gross_profit = next(
        row for row in rows if row["observation_id"] == "fastenal_2025_q1_gross_profit"
    )
    gross_profit["value"] = "883.8"
    candidate = tmp_path / "broken_gross_profit.csv"
    _write_candidate(candidate, rows)

    report = module.validate_public_truth_case(BENCHMARK, candidate)

    assert report["status"] == "failed"
    assert report["counts"]["mismatched"] == 1
    identity = _assertion(report, "gross_profit_identity")
    assert identity["status"] == "failed"
    assert identity["difference"] == "0.1"


def test_public_truth_validator_rejects_duplicate_observation(
    tmp_path: Path,
) -> None:
    module = _load_module()
    rows = _read_candidate_rows()
    rows.append(dict(rows[0]))
    candidate = tmp_path / "duplicate_observation.csv"
    _write_candidate(candidate, rows)

    report = module.validate_public_truth_case(BENCHMARK, candidate)

    assert report["status"] == "failed"
    assert report["counts"]["duplicates"] == 1
    assert report["errors"] == [
        "duplicate candidate observation_id: fastenal_2025_01_net_sales"
    ]


def test_public_truth_validator_rejects_surplus_csv_value(tmp_path: Path) -> None:
    module = _load_module()
    lines = EXPECTED.read_text(encoding="utf-8").splitlines()
    lines[1] = f"{lines[1]},surplus"
    candidate = tmp_path / "surplus_value.csv"
    candidate.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="values beyond the declared columns"):
        module.validate_public_truth_case(BENCHMARK, candidate)


def test_public_truth_validator_rejects_unknown_source(tmp_path: Path) -> None:
    module = _load_module()
    rows = _read_candidate_rows()
    rows[0]["source_id"] = "unknown_source"
    candidate = tmp_path / "unknown_source.csv"
    _write_candidate(candidate, rows)

    with pytest.raises(ValueError, match="references unknown sources"):
        module.validate_public_truth_case(BENCHMARK, candidate)


def test_public_truth_report_is_independent_of_candidate_filename(
    tmp_path: Path,
) -> None:
    module = _load_module()
    first_candidate = tmp_path / "first_name.csv"
    second_candidate = tmp_path / "second_name.csv"
    shutil.copyfile(EXPECTED, first_candidate)
    shutil.copyfile(EXPECTED, second_candidate)

    first_report = module.validate_public_truth_case(BENCHMARK, first_candidate)
    second_report = module.validate_public_truth_case(BENCHMARK, second_candidate)

    assert first_report == second_report


def test_public_truth_validator_rejects_corrupt_fixture_digest(
    tmp_path: Path,
) -> None:
    module = _load_module()
    copied_case = tmp_path / "fastenal_q1_2025"
    shutil.copytree(CASE_ROOT, copied_case)
    copied_benchmark = copied_case / "benchmark.json"
    benchmark = json.loads(copied_benchmark.read_text(encoding="utf-8"))
    benchmark["files"]["truth"]["sha256"] = "0" * 64
    copied_benchmark.write_text(json.dumps(benchmark), encoding="utf-8")

    with pytest.raises(ValueError, match="truth digest mismatch"):
        module.validate_public_truth_case(
            copied_benchmark,
            copied_case / EXPECTED.name,
        )


def test_public_truth_validator_cli_writes_report(tmp_path: Path) -> None:
    module = _load_module()
    output = tmp_path / "validation.json"

    exit_code = module.main(
        [
            str(BENCHMARK),
            str(EXPECTED),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["benchmark_passed"] is True
    assert payload["downstream_readiness"]["status"] == "not_assessed"
    assert "ready_for_downstream" not in payload
    assert str(tmp_path) not in output.read_text(encoding="utf-8")
