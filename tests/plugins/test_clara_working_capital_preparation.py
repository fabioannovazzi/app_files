from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
CASE_ROOT = CLARA_ROOT / "evals" / "preparation" / "wd40_fy2025_working_capital"
CASE_PATH = CASE_ROOT / "case.json"
EXPECTED_ROOT = CASE_ROOT / "expected"
PREPARER_PATH = SCRIPTS_ROOT / "prepare_working_capital_case.py"
ADAPTER_PATH = SCRIPTS_ROOT / "build_working_capital_audit_envelope.py"
AUDIT_SCHEMA_PATH = (
    CLARA_ROOT / "contracts" / "preparation_audit_envelope.v1.schema.json"
)


def _load_module(name: str, path: Path) -> Any:
    scripts_path = str(SCRIPTS_ROOT)
    inserted = scripts_path not in sys.path
    if inserted:
        sys.path.insert(0, scripts_path)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_path)


PREPARER = _load_module("clara_working_capital_preparer_test", PREPARER_PATH)
ADAPTER = _load_module("clara_working_capital_adapter_test", ADAPTER_PATH)
KERNEL = sys.modules["preparation_contract_kernel"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    assert rows
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _copy_case(target: Path) -> Path:
    shutil.copytree(CASE_ROOT, target)
    return target / "case.json"


def _case_asset(case_path: Path, file_id: str) -> Path:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    return case_path.parent / case["files"][file_id]["path"]


def _reseal_case_asset(case_path: Path, file_id: str) -> None:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    asset = case_path.parent / case["files"][file_id]["path"]
    case["files"][file_id]["sha256"] = _sha256(asset)
    _write_json(case_path, case)


def _mutate_csv_row(
    path: Path,
    predicate: Callable[[dict[str, str]], bool],
    updates: dict[str, str],
) -> None:
    rows = _read_csv(path)
    matches = [row for row in rows if predicate(row)]
    assert len(matches) == 1
    matches[0].update(updates)
    _write_csv(path, rows)


def _prepare(case_path: Path, output_dir: Path) -> dict[str, Any]:
    return PREPARER.prepare_working_capital_case(case_path, output_dir)


def _error_codes(result: dict[str, Any]) -> set[str]:
    return {str(error["code"]) for error in result["errors"]}


def _schema_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(AUDIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def test_working_capital_preparation_emits_exact_withheld_outputs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"

    result = _prepare(CASE_PATH, output_dir)

    assert result["status"] == "passed"
    assert result["report_ready"] is False
    assert result["publication_status"] == "withheld"
    assert result["row_lineage_declared"] is False
    assert result["semantic_authority"] == "unproven"
    assert result["source_authority"] == "unproven"
    assert result["counts"] == {
        "raw_fact_rows": 75,
        "balance_sheet_fact_rows": 55,
        "cash_flow_fact_rows": 20,
        "balance_sheet_periods": 5,
        "cash_flow_cumulative_periods": 4,
        "schedule_rows": 5,
        "discrete_cash_flow_rows": 4,
        "bridge_rows": 5,
        "exception_rows": 0,
        "errors": 0,
    }
    assert all(check["status"] == "passed" for check in result["checks"])
    assert {path.name for path in output_dir.iterdir()} == {
        "discrete_cash_flow_schedule.csv",
        "exceptions.csv",
        "prepared_evidence_manifest.json",
        "raw_fact_preservation.csv",
        "reconciliation.json",
        "stock_flow_bridge.csv",
        "working_capital_schedule.csv",
    }
    assert (output_dir / "raw_fact_preservation.csv").read_bytes() == (
        CASE_ROOT / "public_working_capital_facts.csv"
    ).read_bytes()

    schedule = _read_csv(output_dir / "working_capital_schedule.csv")
    assert [row["operating_nwc"] for row in schedule] == [
        "115455",
        "125962",
        "137812",
        "131921",
        "126226",
    ]
    assert [row["delta_operating_nwc"] for row in schedule[1:]] == [
        "10507",
        "11850",
        "-5891",
        "-5695",
    ]
    assert [row["expected_cash_impact"] for row in schedule[1:]] == [
        "-10507",
        "-11850",
        "5891",
        "5695",
    ]

    discrete = _read_csv(output_dir / "discrete_cash_flow_schedule.csv")
    assert [row["discrete_cash_flow_change"] for row in discrete] == [
        "-10805",
        "-13677",
        "9757",
        "4120",
    ]
    assert [row["period_start"] for row in discrete] == [
        "2024-09-01",
        "2024-12-01",
        "2025-03-01",
        "2025-06-01",
    ]
    assert discrete[1] == {
        "quarter": "FY2025-Q2",
        "period_start": "2024-12-01",
        "period_end": "2025-02-28",
        "trade_and_other_accounts_receivable_change": "1829",
        "inventory_change": "-5858",
        "other_assets_change": "-7894",
        "accounts_payable_and_accrued_liabilities_change": "1692",
        "accrued_payroll_and_related_expenses_change": "-3446",
        "cumulative_cash_flow_change": "-24482",
        "prior_cumulative_cash_flow_change": "-10805",
        "discrete_cash_flow_change": "-13677",
        "unit": "USD_thousands",
        "source_sign_convention": ("cash_impact_native_positive_source_negative_use"),
        "current_cumulative_source_id": "wd40_q2_fy2025_10q",
        "prior_cumulative_source_id": "wd40_q1_fy2025_10q",
        "policy_id": "wd40_fy2025_operating_working_capital",
    }
    assert _read_csv(output_dir / "exceptions.csv") == []

    bridge = _read_csv(output_dir / "stock_flow_bridge.csv")
    assert [row["period_cash_flow_change"] for row in bridge[:4]] == [
        "-10805",
        "-13677",
        "9757",
        "4120",
    ]
    assert [row["period_start"] for row in bridge[:4]] == [
        "2024-09-01",
        "2024-12-01",
        "2025-03-01",
        "2025-06-01",
    ]
    assert [row["stock_flow_residual"] for row in bridge[:4]] == [
        "-298",
        "-1827",
        "3866",
        "-1575",
    ]
    assert bridge[-1]["stock_flow_residual"] == "166"
    assert {row["residual_status"] for row in bridge} == {"unexplained"}
    assert all(
        prohibited not in ",".join(bridge[0]).lower()
        for prohibited in ("dso", "dio", "dpo", "target", "normalization")
    )

    manifest = json.loads(
        (output_dir / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["report_ready"] is False
    assert manifest["publication_status"] == "withheld"
    assert manifest["lineage"]["row_lineage_declared"] is False
    assert manifest["lineage"]["row_lineage_records"] == []
    assert manifest["boundaries"]["residual_allocation_emitted"] is False
    assert manifest["boundaries"]["residual_status"] == "unexplained"
    assert manifest["boundaries"]["prohibited_analytics_emitted"] == []
    assert manifest["recipe"]["engine_sha256"] == _sha256(PREPARER_PATH)
    assert {path.name: path.read_bytes() for path in sorted(output_dir.iterdir())} == {
        path.name: path.read_bytes() for path in sorted(EXPECTED_ROOT.iterdir())
    }


def test_working_capital_preparation_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = _prepare(CASE_PATH, first_dir)
    second = _prepare(CASE_PATH, second_dir)

    assert first == second
    assert {path.name: path.read_bytes() for path in sorted(first_dir.iterdir())} == {
        path.name: path.read_bytes() for path in sorted(second_dir.iterdir())
    }


def test_working_capital_preparation_rejects_unregistered_output_entry(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    stale_success = output_dir / "reconciliation.json"
    stale_success.write_text('{"status":"passed"}\n', encoding="utf-8")
    unregistered = output_dir / "analyst-notes.txt"
    unregistered.write_text("not a producer artifact\n", encoding="utf-8")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="output directory must be dedicated",
    ):
        _prepare(CASE_PATH, output_dir)

    assert not stale_success.exists()
    assert unregistered.read_text(encoding="utf-8") == "not a producer artifact\n"


def test_working_capital_audit_adapter_emits_bounded_envelope() -> None:
    envelope = ADAPTER.build_working_capital_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )

    _schema_validator().validate(envelope)
    assert envelope["case"]["case_id"] == "wd40-fy2025-public-working-capital"
    assert envelope["statuses"]["validation"]["status"] == "passed"
    assert envelope["statuses"]["preparation"]["status"] == "passed"
    assert envelope["statuses"]["reconciliation"]["status"] == "passed"
    assert envelope["statuses"]["semantic"]["status"] == "not_assessed"
    assert envelope["statuses"]["source"]["status"] == "receipt_only"
    assert envelope["statuses"]["downstream"]["status"] == "not_assessed"
    assert envelope["statuses"]["publication"]["status"] == "withheld"
    assert envelope["report_ready"] is False
    assert envelope["lineage"]["aggregate"]["declared"] is False
    assert envelope["lineage"]["row"]["declared"] is False
    assert envelope["lineage"]["row"]["records"] == []
    assert len(envelope["reviewed_decisions"]) == 1
    assert envelope["reviewed_decisions"][0]["status"] == "reviewed"
    assert {source["receipt_scope"] for source in envelope["remote_sources"]} == {
        "declared_remote_receipt"
    }


def test_working_capital_audit_adapter_is_deterministic() -> None:
    first = ADAPTER.build_working_capital_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )
    second = ADAPTER.build_working_capital_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )

    assert first == second


def test_working_capital_audit_adapter_rejects_tampered_output(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)
    schedule_path = output_dir / "working_capital_schedule.csv"
    schedule_path.write_bytes(schedule_path.read_bytes() + b"\n")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="does not match deterministic replay",
    ):
        ADAPTER.build_working_capital_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=CASE_PATH,
            prepared_output_dir=output_dir,
        )


def test_working_capital_audit_adapter_rejects_unregistered_output_entry(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)
    (output_dir / "analyst-notes.txt").write_text(
        "not a producer artifact\n",
        encoding="utf-8",
    )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="output set does not match deterministic replay",
    ):
        ADAPTER.build_working_capital_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=CASE_PATH,
            prepared_output_dir=output_dir,
        )


def test_working_capital_duplicate_facts_emit_real_failure_artifacts() -> None:
    with TemporaryDirectory(prefix=".m5b-failed-", dir=CLARA_ROOT) as raw_dir:
        run_root = Path(raw_dir)
        case_path = _copy_case(run_root / "case")
        facts_path = _case_asset(case_path, "public_working_capital_facts")
        rows = _read_csv(facts_path)
        rows.append(dict(rows[0]))
        _write_csv(facts_path, rows)
        _reseal_case_asset(case_path, "public_working_capital_facts")
        output_dir = run_root / "prepared"
        shutil.copytree(EXPECTED_ROOT, output_dir)

        result = _prepare(case_path, output_dir)
        envelope = ADAPTER.build_working_capital_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=case_path,
            prepared_output_dir=output_dir,
        )

        assert result["status"] == "failed"
        assert {
            "duplicate_fact_id",
            "duplicate_fact_natural_key",
        }.issubset(_error_codes(result))
        assert {path.name for path in output_dir.iterdir()} == {
            "exceptions.csv",
            "raw_fact_preservation.csv",
            "reconciliation.json",
        }
        exception_rows = _read_csv(output_dir / "exceptions.csv")
        assert len(exception_rows) == result["counts"]["errors"]
        assert (output_dir / "raw_fact_preservation.csv").read_bytes() == (
            facts_path.read_bytes()
        )
        _schema_validator().validate(envelope)
        assert envelope["statuses"]["validation"]["status"] == "failed"
        assert envelope["statuses"]["preparation"]["status"] == "failed"
        assert envelope["statuses"]["reconciliation"]["status"] == "failed"
        assert envelope["statuses"]["publication"]["status"] == "withheld"
        assert envelope["report_ready"] is False
        assert envelope["lineage"]["row"]["declared"] is False


@pytest.mark.parametrize(
    ("fact_id", "updates", "expected_code"),
    [
        (
            "bs_02_trade_receivables",
            {"unit": "USD"},
            "fact_unit_mismatch",
        ),
        (
            "bs_02_trade_receivables",
            {"source_value": "111433.5"},
            "fact_increment_mismatch",
        ),
        (
            "bs_02_trade_receivables",
            {"period_end": "2024-12-01"},
            "unknown_fact_period",
        ),
        (
            "bs_02_trade_receivables",
            {"source_id": "wd40_q2_fy2025_10q"},
            "fact_source_mismatch",
        ),
        (
            "bs_02_trade_receivables",
            {"source_locator": ""},
            "missing_source_locator",
        ),
        (
            "bs_02_trade_receivables",
            {
                "source_sign_convention": (
                    "cash_impact_native_positive_source_negative_use"
                )
            },
            "fact_sign_convention_mismatch",
        ),
        (
            "cf_01_other_assets",
            {
                "fact_key": "other_current_assets",
                "source_caption": "Other current assets",
            },
            "unexpected_fact_key",
        ),
        (
            "cf_01_accounts_payable_and_accrued",
            {
                "fact_key": "accounts_payable",
                "source_caption": "Accounts payable",
            },
            "unexpected_fact_key",
        ),
        (
            "bs_02_trade_receivables",
            {"source_value": "111434"},
            "current_assets_do_not_foot",
        ),
        (
            "cf_02_trade_receivables",
            {"source_value": "1537"},
            "quarter_bridge_control_mismatch",
        ),
        (
            "cf_02_trade_receivables",
            {"source_value": "1e3"},
            "invalid_source_value",
        ),
    ],
)
def test_working_capital_adversarial_public_fact_changes_fail_closed(
    tmp_path: Path,
    fact_id: str,
    updates: dict[str, str],
    expected_code: str,
) -> None:
    case_path = _copy_case(tmp_path / "case")
    facts_path = _case_asset(case_path, "public_working_capital_facts")
    _mutate_csv_row(
        facts_path,
        lambda row: row["fact_id"] == fact_id,
        updates,
    )
    _reseal_case_asset(case_path, "public_working_capital_facts")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert expected_code in _error_codes(result)
    assert result["publication_status"] == "withheld"
    assert result["report_ready"] is False
    assert result["residual_treatment"]["allocation_emitted"] is False
    assert result["residual_treatment"]["status"] == "unexplained"


def test_working_capital_omitted_fact_fails_closed(tmp_path: Path) -> None:
    case_path = _copy_case(tmp_path / "case")
    facts_path = _case_asset(case_path, "public_working_capital_facts")
    rows = _read_csv(facts_path)
    rows = [row for row in rows if row["fact_id"] != "bs_02_trade_receivables"]
    _write_csv(facts_path, rows)
    _reseal_case_asset(case_path, "public_working_capital_facts")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "missing_required_fact" in _error_codes(result)
    assert {path.name for path in (tmp_path / "prepared").iterdir()} == {
        "exceptions.csv",
        "raw_fact_preservation.csv",
        "reconciliation.json",
    }


def test_working_capital_extra_fact_fails_closed(tmp_path: Path) -> None:
    case_path = _copy_case(tmp_path / "case")
    facts_path = _case_asset(case_path, "public_working_capital_facts")
    rows = _read_csv(facts_path)
    duplicate = dict(rows[0])
    duplicate["fact_id"] = "bs_01_accounts_payable_extra"
    rows.append(duplicate)
    _write_csv(facts_path, rows)
    _reseal_case_asset(case_path, "public_working_capital_facts")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "duplicate_fact_natural_key" in _error_codes(result)
    assert {path.name for path in (tmp_path / "prepared").iterdir()} == {
        "exceptions.csv",
        "raw_fact_preservation.csv",
        "reconciliation.json",
    }


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda policy: policy["review"].update({"status": "draft"}),
            "policy_not_reviewed",
        ),
        (
            lambda policy: policy["stock_flow_bridge_policy"].update(
                {"force_residual_to_zero": True}
            ),
            "residual_policy_mismatch",
        ),
        (
            lambda policy: policy["balance_sheet_policy"]["formula_terms"][0].update(
                {"multiplier": "-1"}
            ),
            "operating_nwc_formula_mismatch",
        ),
        (
            lambda policy: policy["caption_boundaries"].update(
                {
                    "cash_flow_other_assets_equals_balance_sheet_other_current_assets": (
                        True
                    )
                }
            ),
            "caption_boundary_mismatch",
        ),
        (
            lambda policy: policy["cash_flow_policy"].update(
                {"de_cumulation": "use_current_cumulative_without_subtraction"}
            ),
            "cash_flow_de_cumulation_policy_mismatch",
        ),
    ],
)
def test_working_capital_adversarial_policy_changes_fail_closed(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    case_path = _copy_case(tmp_path / "case")
    policy_path = _case_asset(case_path, "reviewed_working_capital_policy")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    mutator(policy)
    _write_json(policy_path, policy)
    _reseal_case_asset(case_path, "reviewed_working_capital_policy")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert expected_code in _error_codes(result)
    assert {path.name for path in (tmp_path / "prepared").iterdir()} == {
        "exceptions.csv",
        "raw_fact_preservation.csv",
        "reconciliation.json",
    }


def test_working_capital_rejects_unsealed_input_change_before_outputs(
    tmp_path: Path,
) -> None:
    case_path = _copy_case(tmp_path / "case")
    facts_path = _case_asset(case_path, "public_working_capital_facts")
    facts_path.write_bytes(facts_path.read_bytes() + b"\n")
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="public_working_capital_facts digest mismatch",
    ):
        _prepare(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_working_capital_rejects_truncated_fact_row_before_outputs(
    tmp_path: Path,
) -> None:
    case_path = _copy_case(tmp_path / "case")
    facts_path = _case_asset(case_path, "public_working_capital_facts")
    lines = facts_path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].rsplit(",", maxsplit=1)[0]
    facts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _reseal_case_asset(case_path, "public_working_capital_facts")
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="truncated cells",
    ):
        _prepare(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_working_capital_rejects_unregistered_engine_version_and_clears_outputs(
    tmp_path: Path,
) -> None:
    case_path = _copy_case(tmp_path / "case")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["preparation_recipe"]["engine_version"] = "99.0.0"
    _write_json(case_path, case)
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="preparation_recipe.engine_version must be",
    ):
        _prepare(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_working_capital_adapter_rejects_stale_success_after_input_change(
    tmp_path: Path,
) -> None:
    case_path = _copy_case(tmp_path / "case")
    facts_path = _case_asset(case_path, "public_working_capital_facts")
    _mutate_csv_row(
        facts_path,
        lambda row: row["fact_id"] == "bs_02_trade_receivables",
        {"source_value": "111434"},
    )
    _reseal_case_asset(case_path, "public_working_capital_facts")
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="output set does not match deterministic replay",
    ):
        ADAPTER.build_working_capital_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=case_path,
            prepared_output_dir=output_dir,
        )


def test_working_capital_audit_cli_removes_stale_output_on_failure(
    tmp_path: Path,
) -> None:
    prepared_output = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, prepared_output)
    bridge_path = prepared_output / "stock_flow_bridge.csv"
    bridge_path.write_bytes(bridge_path.read_bytes() + b"\n")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text('{"stale":"passed"}\n', encoding="utf-8")

    exit_code = ADAPTER.main(
        [
            str(CASE_PATH),
            str(prepared_output),
            "--output",
            str(audit_path),
            "--clara-root",
            str(CLARA_ROOT),
        ]
    )

    assert exit_code == 2
    assert not audit_path.exists()
