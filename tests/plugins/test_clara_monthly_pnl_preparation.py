from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
CASE_ROOT = CLARA_ROOT / "evals" / "preparation" / "wd40_fy2025"
CASE_PATH = CASE_ROOT / "case.json"
EXPECTED_ROOT = CASE_ROOT / "expected"
PREPARATION_SCRIPT = CLARA_ROOT / "scripts" / "prepare_monthly_pnl_case.py"
STATEMENT_RECIPE = CASE_ROOT / "statement_render_recipe.json"
REPORTING_ENGINE_ROOT = CLARA_ROOT / "modules" / "reporting-engine"
RENDERER_PATH = REPORTING_ENGINE_ROOT / "scripts" / "render_capability.py"
EVIDENCE_PATH = CLARA_ROOT / "skills" / "html-deck" / "scripts" / "evidence_bindings.py"

EXPECTED_OUTPUT_HASHES = {
    "monthly_pnl.csv": "ad7b2f1b2267ece697d7ec1cce9e0155da68ae10d5a8eeb7100823fda28bf1a0",
    "reconciliation.json": "4dd146d25196b79a24f70c9363b73623c55bf600359d4c70239815db2e6126a4",
    "unmapped_accounts.csv": "4268cab92c65ff567104c2243854a0cc6722b0eaaa61f9544e57c2bc098c0052",
}
EXPECTED_MANIFEST_SHA256 = (
    "a1784ad9a4ce33ed4090c9e9e6e036382ea4a628080fcd8526ae24d5afe271c3"
)
EXPECTED_STATEMENT_ROWS = (
    "net_sales",
    "cost_of_products_sold",
    "gross_profit",
    "selling_general_and_administrative",
    "advertising_and_sales_promotion",
    "amortization_of_definite_lived_intangible_assets",
    "total_operating_expenses",
    "income_from_operations",
    "interest_income",
    "interest_expense",
    "other_income_expense_net",
    "income_before_income_taxes",
    "provision_for_income_taxes",
    "net_income",
)
EXPECTED_SOURCE_RECEIPTS = {
    "wd40_q1_fy2025_10q": {
        "accession": "0000105132-25-000009",
        "filed_date": "2025-01-10",
        "byte_count": 1030161,
        "sha256": "b7a1534f188f6e30b4d24cae3e173d3cda7d68b6c40f5aa24af19c3654daa70f",
    },
    "wd40_q2_fy2025_10q": {
        "accession": "0000105132-25-000015",
        "filed_date": "2025-04-09",
        "byte_count": 1405347,
        "sha256": "e013e12e87e4a0ad38f12194823eff81d17f9cb880a0b3a09146e0359fda3707",
    },
    "wd40_q3_fy2025_10q": {
        "accession": "0000105132-25-000025",
        "filed_date": "2025-07-10",
        "byte_count": 1435323,
        "sha256": "cafdc1640c715179b956f05e502333229b129d5a4e0a0c4c0beed18844cb253d",
    },
    "wd40_q4_fy2025_exhibit_99_1": {
        "accession": "0000105132-25-000061",
        "filed_date": "2025-10-22",
        "byte_count": 238878,
        "sha256": "df9040b54e65e635d114c0414468f6779fb440b32de7ead30b35f6c49b600710",
    },
    "wd40_fy2025_10k": {
        "accession": "0000105132-25-000067",
        "filed_date": "2025-10-27",
        "byte_count": 1793208,
        "sha256": "d03a7ef37c6796c1a01d6b9bdb438afb6b276abfa5baa112b9b0465b4fe83209",
    },
}


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _preparation_module() -> Any:
    return _load_module(
        "clara_monthly_pnl_preparation_test",
        PREPARATION_SCRIPT,
    )


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


def _copy_case(tmp_path: Path) -> tuple[Path, Path]:
    copied_root = tmp_path / "wd40_fy2025"
    shutil.copytree(CASE_ROOT, copied_root)
    return copied_root, copied_root / "case.json"


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


def _error_codes(result: dict[str, Any]) -> set[str]:
    return {str(error["code"]) for error in result["errors"]}


def _monthly_value(
    rows: list[dict[str, str]],
    row_key: str,
    period: str,
) -> str:
    matches = [
        row for row in rows if row["row_key"] == row_key and row["period"] == period
    ]
    assert len(matches) == 1
    return matches[0]["value"]


def _public_tie_out(
    result: dict[str, Any],
    period: str,
    row_key: str,
) -> dict[str, str]:
    matches = [
        item
        for item in result["public_tie_outs"]
        if item["period"] == period and item["row_key"] == row_key
    ]
    assert len(matches) == 1
    return matches[0]


def _prepare(case_path: Path, output_dir: Path) -> dict[str, Any]:
    return _preparation_module().prepare_monthly_pnl_case(case_path, output_dir)


def _source_receipts(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(source["source_id"]): {
            "accession": source["accession"],
            "filed_date": source["filed_date"],
            "byte_count": source["byte_count"],
            "sha256": source["sha256"],
        }
        for source in sources
    }


def test_monthly_pnl_preparation_emits_exact_reconciled_outputs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"

    result = _prepare(CASE_PATH, output_dir)

    assert result["status"] == "passed"
    assert result["publication_status"] == "synthetic_benchmark_only"
    assert result["counts"] == {
        "errors": 0,
        "mapped_included_rows": 132,
        "leaf_conservation_results": 108,
        "mapping_fanout_rows": 0,
        "mapping_row_ids": 12,
        "mapping_rows": 12,
        "mapping_rows_used": 12,
        "monthly_identity_results": 60,
        "monthly_periods": 12,
        "monthly_pnl_rows": 168,
        "public_tie_out_results": 70,
        "reviewed_excluded_rows": 12,
        "source_rows": 144,
        "statement_lines": 14,
        "trial_balance_accounts": 12,
        "unique_source_row_ids": 144,
        "unmapped_rows": 0,
        "unresolved_rows": 0,
    }
    assert all(check["status"] == "passed" for check in result["checks"])
    assert {item["difference"] for item in result["monthly_statement_identities"]} == {
        "0"
    }
    assert {item["difference"] for item in result["public_tie_outs"]} == {"0"}
    assert result["source_row_conservation"] == {
        "input_rows": 144,
        "classified_rows": 144,
        "unresolved_rows": 0,
        "mapping_fanout_rows": 0,
        "status": "passed",
    }
    assert len(result["leaf_aggregation_conservation"]) == 108
    assert {item["difference"] for item in result["leaf_aggregation_conservation"]} == {
        "0"
    }
    assert (
        sum(
            item["source_row_count"] for item in result["leaf_aggregation_conservation"]
        )
        == 132
    )
    assert result["downstream_readiness"] == {
        "status": "not_assessed",
        "report_ready": False,
        "semantic_compatibility": "not_assessed",
        "render_compatibility": "not_assessed",
        "evidence_sealing": "not_assessed",
    }

    monthly_rows = _read_csv(output_dir / "monthly_pnl.csv")
    assert len(monthly_rows) == 168
    assert (
        len({(row["row_key"], row["period"], row["scenario"]) for row in monthly_rows})
        == 168
    )
    assert {row["scenario"] for row in monthly_rows} == {"SYN"}
    assert {row["unit"] for row in monthly_rows} == {"USD_thousands"}
    assert _monthly_value(monthly_rows, "net_sales", "2024-09") == "51000"
    assert _monthly_value(monthly_rows, "gross_profit", "2024-09") == "27900"
    assert _monthly_value(monthly_rows, "net_income", "2024-09") == "6294"
    assert (
        _monthly_value(
            monthly_rows,
            "provision_for_income_taxes",
            "2025-02",
        )
        == "-2462"
    )
    assert _monthly_value(monthly_rows, "net_income", "2025-08") == "6496"
    assert _read_csv(output_dir / "unmapped_accounts.csv") == []
    assert {
        filename: _sha256(output_dir / filename) for filename in EXPECTED_OUTPUT_HASHES
    } == EXPECTED_OUTPUT_HASHES
    assert (
        _sha256(output_dir / "prepared_evidence_manifest.json")
        == EXPECTED_MANIFEST_SHA256
    )
    assert {path.name: path.read_bytes() for path in sorted(output_dir.iterdir())} == {
        path.name: path.read_bytes() for path in sorted(EXPECTED_ROOT.iterdir())
    }

    manifest = json.loads(
        (output_dir / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["preparation_status"] == "passed"
    assert manifest["publication_status"] == "synthetic_benchmark_only"
    assert (
        manifest["disclosure_boundary"]["monthly_values_are_company_actuals"] is False
    )
    assert manifest["downstream_readiness"]["report_ready"] is False
    assert manifest["recipe"]["engine_sha256"] == _sha256(PREPARATION_SCRIPT)
    assert manifest["lineage"]["base_statement_line_accounts"]["net_sales"] == [
        "4000",
        "4010",
    ]
    assert manifest["lineage"]["base_statement_line_accounts"][
        "cost_of_products_sold"
    ] == ["5000", "5010"]
    case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    assert _source_receipts(case["sources"]) == EXPECTED_SOURCE_RECEIPTS
    assert _source_receipts(manifest["source_receipts"]) == EXPECTED_SOURCE_RECEIPTS
    artifact_hashes = {
        artifact["path"]: artifact["sha256"] for artifact in manifest["outputs"]
    }
    assert artifact_hashes == EXPECTED_OUTPUT_HASHES


def test_monthly_pnl_preparation_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = _prepare(CASE_PATH, first)
    second_result = _prepare(CASE_PATH, second)

    assert first_result == second_result
    assert {path.name: path.read_bytes() for path in sorted(first.iterdir())} == {
        path.name: path.read_bytes() for path in sorted(second.iterdir())
    }


def test_monthly_pnl_preparation_rejects_duplicate_source_row(
    tmp_path: Path,
) -> None:
    copied_root, case_path = _copy_case(tmp_path)
    trial_balance = _case_asset(case_path, "synthetic_monthly_trial_balance")
    rows = _read_csv(trial_balance)
    rows.append(dict(rows[0]))
    _write_csv(trial_balance, rows)
    _reseal_case_asset(case_path, "synthetic_monthly_trial_balance")
    output_dir = tmp_path / "prepared"

    result = _prepare(case_path, output_dir)

    assert result["status"] == "failed"
    assert {
        "duplicate_source_row_id",
        "duplicate_trial_balance_natural_key",
    }.issubset(_error_codes(result))
    assert not (output_dir / "monthly_pnl.csv").exists()
    assert not (output_dir / "prepared_evidence_manifest.json").exists()
    assert (output_dir / "reconciliation.json").exists()
    assert copied_root.exists()


def test_monthly_pnl_preparation_rejects_unmapped_account(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    trial_balance = _case_asset(case_path, "synthetic_monthly_trial_balance")
    _mutate_csv_row(
        trial_balance,
        lambda row: row["source_row_id"] == "tb-2024-09-4000",
        {
            "account_code": "4999",
            "account_name": "Unmapped synthetic sales",
        },
    )
    _reseal_case_asset(case_path, "synthetic_monthly_trial_balance")
    output_dir = tmp_path / "prepared"

    result = _prepare(case_path, output_dir)

    assert result["status"] == "failed"
    assert "unmapped_account" in _error_codes(result)
    assert result["counts"]["unmapped_rows"] == 1
    assert _read_csv(output_dir / "unmapped_accounts.csv") == [
        {
            "source_row_id": "tb-2024-09-4000",
            "scope_id": "wd40_fy2025_synthetic_consolidated",
            "entity_id": "wd40_company_synthetic_entity",
            "account_code": "4999",
            "account_name": "Unmapped synthetic sales",
            "period": "2024-09",
            "period_start": "2024-09-01",
            "period_end": "2024-09-30",
            "source_value": "-30600",
            "unit": "USD_thousands",
            "reason": "account_absent_from_reviewed_mapping",
        }
    ]
    assert not (output_dir / "monthly_pnl.csv").exists()


def test_monthly_pnl_preparation_rejects_mapping_sign_change(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    mapping = _case_asset(case_path, "reviewed_coa_mapping")
    _mutate_csv_row(
        mapping,
        lambda row: row["mapping_row_id"] == "map-4000-v1",
        {"presentation_multiplier": "1"},
    )
    _reseal_case_asset(case_path, "reviewed_coa_mapping")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "mapping_sign_mismatch" in _error_codes(result)
    assert "normalized_sign_violation" in _error_codes(result)


@pytest.mark.parametrize(
    ("field", "new_value", "expected_code"),
    [
        ("period_end", "2024-09-29", "period_bounds_mismatch"),
        ("unit", "USD", "unit_mismatch"),
        ("scope_id", "wrong_scope", "trial_balance_scope_mismatch"),
        ("entity_id", "wrong_entity", "trial_balance_scope_mismatch"),
        ("source_classification", "published", "invalid_source_classification"),
    ],
)
def test_monthly_pnl_preparation_rejects_trial_balance_contract_change(
    tmp_path: Path,
    field: str,
    new_value: str,
    expected_code: str,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    trial_balance = _case_asset(case_path, "synthetic_monthly_trial_balance")
    _mutate_csv_row(
        trial_balance,
        lambda row: row["source_row_id"] == "tb-2024-09-4000",
        {field: new_value},
    )
    _reseal_case_asset(case_path, "synthetic_monthly_trial_balance")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert expected_code in _error_codes(result)


@pytest.mark.parametrize(
    ("field", "new_value", "expected_code"),
    [
        ("mapping_version", "wd40-synthetic-coa.v2", "mapping_version_mismatch"),
        ("status", "draft", "mapping_status_not_reviewed"),
        ("effective_start", "2024-10-01", "mapping_effective_gap"),
    ],
)
def test_monthly_pnl_preparation_rejects_mapping_contract_change(
    tmp_path: Path,
    field: str,
    new_value: str,
    expected_code: str,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    mapping = _case_asset(case_path, "reviewed_coa_mapping")
    _mutate_csv_row(
        mapping,
        lambda row: row["mapping_row_id"] == "map-4000-v1",
        {field: new_value},
    )
    _reseal_case_asset(case_path, "reviewed_coa_mapping")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert expected_code in _error_codes(result)


def test_monthly_pnl_preparation_rejects_mapping_fanout(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    mapping = _case_asset(case_path, "reviewed_coa_mapping")
    rows = _read_csv(mapping)
    duplicate = dict(rows[0])
    duplicate["mapping_row_id"] = "map-4000-overlap-v1"
    rows.append(duplicate)
    _write_csv(mapping, rows)
    _reseal_case_asset(case_path, "reviewed_coa_mapping")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "mapping_fanout" in _error_codes(result)
    assert result["counts"]["mapping_fanout_rows"] == 12


def test_monthly_pnl_preparation_rejects_corrupt_input_digest(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["files"]["reviewed_coa_mapping"]["sha256"] = "0" * 64
    _write_json(case_path, case)
    output_dir = tmp_path / "prepared"

    with pytest.raises(ValueError, match="reviewed_coa_mapping digest mismatch"):
        _prepare(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_monthly_pnl_preparation_rejects_multi_month_final_period(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["preparation_recipe"]["periods"][-1]["period_end"] = "2025-09-30"
    _write_json(case_path, case)

    with pytest.raises(ValueError, match="complete calendar month"):
        _prepare(case_path, tmp_path / "prepared")


def test_monthly_pnl_preparation_rejects_truncated_csv_row(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    mapping = _case_asset(case_path, "reviewed_coa_mapping")
    lines = mapping.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].rsplit(",", maxsplit=1)[0]
    mapping.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _reseal_case_asset(case_path, "reviewed_coa_mapping")

    with pytest.raises(ValueError, match="does not match the declared columns"):
        _prepare(case_path, tmp_path / "prepared")


def test_monthly_pnl_preparation_rejects_duplicate_case_json_field(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    text = case_path.read_text(encoding="utf-8")
    duplicate = (
        '  "case_id": "duplicate-case-id",\n'
        '  "case_id": "wd40-fy2025-synthetic-monthly-pnl",'
    )
    case_path.write_text(
        text.replace(
            '  "case_id": "wd40-fy2025-synthetic-monthly-pnl",',
            duplicate,
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON field 'case_id'"):
        _prepare(case_path, tmp_path / "prepared")


def test_monthly_pnl_preparation_rejects_wrong_source_role_for_period(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["preparation_recipe"]["public_periods"][0]["source_id"] = "wd40_fy2025_10k"
    _write_json(case_path, case)

    with pytest.raises(ValueError, match="must use a quarterly_control source"):
        _prepare(case_path, tmp_path / "prepared")


def test_monthly_pnl_preparation_rejects_public_value_off_increment(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    public_facts = _case_asset(case_path, "public_statement_facts")
    _mutate_csv_row(
        public_facts,
        lambda row: row["fact_id"] == "wd40_fy2025_q1_net_sales",
        {"source_value": "153495.5", "value": "153495.5"},
    )
    _reseal_case_asset(case_path, "public_statement_facts")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "public_fact_increment_mismatch" in _error_codes(result)


def test_monthly_pnl_preparation_controls_decimal_context_for_large_values(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    trial_balance = _case_asset(case_path, "synthetic_monthly_trial_balance")
    rows = _read_csv(trial_balance)
    sales = next(row for row in rows if row["source_row_id"] == "tb-2024-09-4000")
    clearing = next(row for row in rows if row["source_row_id"] == "tb-2024-09-9999")
    sales["value"] = "-12345678901234567890123456789"
    clearing["value"] = "12345678901234567890123432483"
    _write_csv(trial_balance, rows)
    _reseal_case_asset(case_path, "synthetic_monthly_trial_balance")

    with localcontext() as context:
        context.prec = 4
        result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "trial_balance_not_zero" not in _error_codes(result)
    assert _public_tie_out(result, "FY2025-Q1", "net_sales") == {
        "period": "FY2025-Q1",
        "period_grain": "quarter",
        "row_key": "net_sales",
        "prepared_value": "12345678901234567890123579684",
        "public_value": "153495",
        "difference": "12345678901234567890123426189",
        "tolerance": "0",
        "status": "failed",
    }


def test_monthly_pnl_preparation_rejects_exact_but_wrong_public_tie_out(
    tmp_path: Path,
) -> None:
    _copied_root, case_path = _copy_case(tmp_path)
    trial_balance = _case_asset(case_path, "synthetic_monthly_trial_balance")
    rows = _read_csv(trial_balance)
    sales = next(row for row in rows if row["source_row_id"] == "tb-2024-09-4000")
    clearing = next(row for row in rows if row["source_row_id"] == "tb-2024-09-9999")
    sales["value"] = "-30601"
    clearing["value"] = "6295"
    _write_csv(trial_balance, rows)
    _reseal_case_asset(case_path, "synthetic_monthly_trial_balance")

    result = _prepare(case_path, tmp_path / "prepared")

    assert result["status"] == "failed"
    assert "trial_balance_not_zero" not in _error_codes(result)
    assert "monthly_statement_identity_failed" not in _error_codes(result)
    assert "public_anchor_mismatch" in _error_codes(result)
    assert all(
        item["status"] == "passed" for item in result["monthly_statement_identities"]
    )


def test_monthly_pnl_preparation_cli_writes_clean_outputs(tmp_path: Path) -> None:
    module = _preparation_module()
    output_dir = tmp_path / "prepared"

    exit_code = module.main(
        [
            str(CASE_PATH),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert {path.name for path in output_dir.iterdir()} == {
        "monthly_pnl.csv",
        "unmapped_accounts.csv",
        "reconciliation.json",
        "prepared_evidence_manifest.json",
    }


def test_monthly_pnl_statement_render_transports_prepared_values(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"
    result = _prepare(CASE_PATH, output_dir)
    assert result["status"] == "passed"
    renderer = _load_module(
        "clara_monthly_pnl_renderer_test",
        RENDERER_PATH,
    )
    request = renderer.RenderRequest(
        capability_id="statement.pnl_table",
        input_file=(output_dir / "monthly_pnl.csv").resolve(),
        output_dir=(tmp_path / "render").resolve(),
        recipe_path=STATEMENT_RECIPE.resolve(),
        role_bindings={
            "period_axis": "period",
            "statement_value": "value",
            "statement_line_item": "row_key",
            "statement_scenario": "scenario",
        },
        artifact_mode="data_and_render",
    )

    render_manifest = renderer.render_capability(
        request,
        root=REPORTING_ENGINE_ROOT,
    )

    assert render_manifest["adapter_id"] == "reporting-engine.statement"
    assert render_manifest["component_name"] == "statement-analysis"
    assert render_manifest["runner"]["status"] == "ok"
    assert render_manifest["render_proof"]["status"] == "rendered"
    assert render_manifest["recipe"]["required_roles"]["status"] == "satisfied"
    assert render_manifest["recipe"]["required_roles"]["missing_roles"] == []
    prepared_manifest = json.loads(
        (output_dir / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    prepared_input_hash = next(
        artifact["sha256"]
        for artifact in prepared_manifest["outputs"]
        if artifact["artifact_id"] == "monthly_pnl"
    )
    assert render_manifest["evidence"]["input"]["sha256"] == prepared_input_hash
    assert len(render_manifest["evidence"]["outputs"]) == 6
    assert all(
        output["sha256"] and output["size_bytes"] > 0
        for output in render_manifest["evidence"]["outputs"]
    )
    used_recipe = json.loads(
        (tmp_path / "render" / "used_recipe.json").read_text(encoding="utf-8")
    )
    assert len(used_recipe["statement_rows"]) == 14
    assert tuple(row["key"] for row in used_recipe["statement_rows"]) == (
        EXPECTED_STATEMENT_ROWS
    )
    assert len(used_recipe["periods"]) == 12
    assert "synthetic" in used_recipe["title"].lower()
    assert "synthetic" in used_recipe["scope_label"].lower()
    assert {
        scenario
        for scenarios in used_recipe["scenarios_by_period"].values()
        for scenario in scenarios
    } == {"SYN"}
    assert all(
        row["source_key"] == row["key"] and "formula" not in row
        for row in used_recipe["statement_rows"]
    )
    chart_rows = _read_csv(tmp_path / "render" / "pnl_statement_table_chart_data.csv")
    assert len(chart_rows) == 14
    prepared_values = {
        (row["row_key"], row["period"]): Decimal(row["value"])
        for row in _read_csv(output_dir / "monthly_pnl.csv")
    }
    rendered_values = {
        (row["key"], period): Decimal(row[f"{period}_SYN"])
        for row in chart_rows
        for period in used_recipe["periods"]
    }
    assert rendered_values == prepared_values


def _binding_template(
    text: str,
    *,
    sales_binding: str,
    gross_binding: str,
) -> dict[str, Any]:
    return {
        "$template": {
            "text": text,
            "bindings": {
                "sales": {"id": sales_binding, "mode": "display"},
                "gross": {"id": gross_binding, "mode": "display"},
            },
        }
    }


def test_monthly_pnl_evidence_bundle_seals_and_resolves_exact_cells(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"
    result = _prepare(CASE_PATH, output_dir)
    assert result["status"] == "passed"
    evidence = _load_module(
        "clara_monthly_pnl_evidence_test",
        EVIDENCE_PATH,
    )
    monthly_pnl = output_dir / "monthly_pnl.csv"
    bundle_path = output_dir / "evidence-bundle.json"
    _write_json(
        bundle_path,
        {
            "schema_version": "clara.evidence_bundle.v1",
            "bundle_id": "wd40-fy2025-monthly-pnl-preparation",
            "description": (
                "Illustrative synthetic monthly calculation output anchored to "
                "public quarter and fiscal-year controls."
            ),
            "artifacts": [
                {
                    "id": "monthly-pnl",
                    "source_id": "source-prepared-monthly-pnl",
                    "path": monthly_pnl.name,
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "wd40-fy2025-synthetic-monthly-pnl-v1",
                    "table": {
                        "key_fields": ["row_key", "period", "scenario"],
                        "order_by": ["display_order", "period"],
                    },
                }
            ],
        },
    )
    sealed = evidence.seal_evidence_bundle(bundle_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    format_contract = {
        "decimals": 0,
        "grouping": True,
        "rounding": "half_up",
        "suffix": " USD thousands",
    }
    bindings = {
        "september-sales": {
            "kind": "table_cell",
            "artifact_id": "monthly-pnl",
            "row_key": {
                "row_key": "net_sales",
                "period": "2024-09",
                "scenario": "SYN",
            },
            "field": "value",
            "value_type": "decimal",
            "display": format_contract,
        },
        "september-gross-profit": {
            "kind": "table_cell",
            "artifact_id": "monthly-pnl",
            "row_key": {
                "row_key": "gross_profit",
                "period": "2024-09",
                "scenario": "SYN",
            },
            "field": "value",
            "value_type": "decimal",
            "display": format_contract,
        },
    }
    statement = _binding_template(
        "Illustrative synthetic sales are {sales}; gross profit is {gross}.",
        sales_binding="september-sales",
        gross_binding="september-gross-profit",
    )
    plan = {
        "schema_version": "clara.html_deck_plan.v2",
        "allow_bespoke_html": False,
        "evidence": {
            "bundle": {
                "path": bundle_path.name,
                "sha256": sealed["sha256"],
            },
            "numeric_policy": "require_bindings",
            "bindings": bindings,
        },
        "slides": [
            {
                "id": "synthetic-preparation",
                "layout_id": "visual-takeaway",
                "title": statement,
                "chapter": "evidence",
                "chapter_label": "Evidence",
                "tone": "light",
                "notes": "Explain that this is illustrative synthetic preparation.",
                "source_refs": ["source-prepared-monthly-pnl"],
                "claim_refs": ["claim-synthetic-values"],
                "slots": {
                    "eyebrow": "Synthetic preparation",
                    "title": statement,
                    "takeaway_label": "Boundary",
                    "takeaway": "Monthly values are illustrative and not issuer actuals.",
                    "source_note": "Prepared from a reviewed synthetic fixture.",
                },
            }
        ],
    }
    ledger = {
        "schema_version": "clara.html_deck_ledger.v2",
        "sources": [
            {
                "id": "source-prepared-monthly-pnl",
                "label": "Synthetic monthly P&L preparation output",
                "kind": "calculation-output",
                "locator": monthly_pnl.name,
                "sha256": _sha256(monthly_pnl),
                "publish_locator": False,
            }
        ],
        "slides": [
            {
                "slide_id": "synthetic-preparation",
                "basis_status": "source-backed",
                "basis_note": "Illustrative synthetic calculation output.",
                "claims": [
                    {
                        "id": "claim-synthetic-values",
                        "statement": statement,
                        "classification": "fact",
                        "basis_status": "source-backed",
                        "basis_note": "Synthetic calculation fact; not issuer-reported.",
                        "source_ids": ["source-prepared-monthly-pnl"],
                    }
                ],
            }
        ],
    }

    resolution = evidence.resolve_source_bound_documents(
        plan=plan,
        ledger=ledger,
        base_dir=output_dir,
    )

    artifact = bundle["artifacts"][0]
    prepared_manifest = json.loads(
        (output_dir / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    prepared_monthly_hash = next(
        output["sha256"]
        for output in prepared_manifest["outputs"]
        if output["artifact_id"] == "monthly_pnl"
    )
    assert artifact["sha256"] == _sha256(monthly_pnl)
    assert artifact["sha256"] == prepared_monthly_hash
    assert artifact["size_bytes"] == monthly_pnl.stat().st_size
    assert sealed["artifact_count"] == 1
    assert resolution.evidence_ledger["status"] == "verified"
    assert resolution.evidence_ledger["artifacts"][0]["sha256"] == _sha256(monthly_pnl)
    binding_uses = resolution.evidence_ledger["bindings"]
    assert {use["binding_id"] for use in binding_uses} == {
        "september-sales",
        "september-gross-profit",
    }
    assert {use["raw_value"] for use in binding_uses} == {"51000", "27900"}
    assert {
        tuple(sorted(use["address"]["row_key"].items())) for use in binding_uses
    } == {
        (
            ("period", "2024-09"),
            ("row_key", "net_sales"),
            ("scenario", "SYN"),
        ),
        (
            ("period", "2024-09"),
            ("row_key", "gross_profit"),
            ("scenario", "SYN"),
        ),
    }
    assert {use["artifact_sha256"] for use in binding_uses} == {_sha256(monthly_pnl)}
    assert {use["source_id"] for use in binding_uses} == {"source-prepared-monthly-pnl"}
    assert {use["value_sha256"] for use in binding_uses} == {
        evidence.sha256_bytes(evidence.canonical_json_bytes("51000")),
        evidence.sha256_bytes(evidence.canonical_json_bytes("27900")),
    }
