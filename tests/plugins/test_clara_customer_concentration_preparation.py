from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
CASE_ROOT = CLARA_ROOT / "evals" / "preparation" / "udc_fy2025_customer_concentration"
CASE_PATH = CASE_ROOT / "case.json"
FACTS_PATH = CASE_ROOT / "exact_extracted_facts.csv"
CONTROL_FACTS_PATH = CASE_ROOT / "exact_control_facts.csv"
EXPECTED_ROOT = CASE_ROOT / "expected"
CONTRACT_SCHEMA = CLARA_ROOT / "contracts" / "preparation_audit_envelope.v1.schema.json"

if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import build_customer_concentration_audit_envelope as AUDIT_ADAPTER  # noqa: E402
import preparation_contract_kernel as KERNEL  # noqa: E402
import prepare_customer_concentration_case as PREPARER  # noqa: E402

EXPECTED_FILE_HASHES = {
    "case.json": "4051affdaf72127968dd0a377eec41be2a403c3ea4201e2c03376be871e680e9",
    "exact_control_facts.csv": (
        "57a84b89c7172e7f8d1497cf1974ae13860289dd44902d83302deb66812f25f8"
    ),
    "exact_extracted_facts.csv": (
        "784a2785e5f3a17f4c3382ca61a669a9f0680139865a202328eb0339b4806be7"
    ),
    "customer_concentration_summary.csv": (
        "48c75363a10a4e5339fee4f3f57b9e27d4005430a7faa099d38ca4e4f94a00f2"
    ),
    "exceptions.csv": (
        "aae96c35ad9098a8580bbc08b841dfb2ae41a374efeb9ce97ad69a7f8eb0b1a3"
    ),
    "prepared_evidence_manifest.json": (
        "f422439cde2c63839b0e812159f91ddddd425d41b4dd19e100200e20ae716120"
    ),
    "reconciliation.json": (
        "27446774176f313a8a1a7f8d72c615e5bf4267c0770dfa1d063843cb5d6135fa"
    ),
}
EXPECTED_ENVELOPE_SHA256 = (
    "3791df39df79ff26f18a5f0589d86fcff2366740e0d5286f667ed53df0222d34"
)
EXPECTED_SOURCE_RECEIPT = {
    "source_id": "udc_fy2025_10k",
    "accession": "0001193125-26-059371",
    "filed_date": "2026-02-19",
    "byte_count": 4060769,
    "sha256": "1dd7a2297816c53f4f90b68736c1317b5aa1c28f0360672e351a603e66909a29",
}
FORBIDDEN_CLAIMS = (
    "precise_customer_revenue_dollars",
    "full_hhi",
    "hhi_lower_bound",
    "monthly_customer_concentration",
    "quarterly_customer_concentration",
    "customer_churn",
    "customer_retention",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_case(tmp_path: Path) -> tuple[Path, Path]:
    copied_root = tmp_path / "udc_fy2025_customer_concentration"
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


def _mutate_row(
    path: Path,
    *,
    row_id_field: str,
    row_id: str,
    updates: dict[str, str],
) -> None:
    rows = _read_csv(path)
    matches = [row for row in rows if row[row_id_field] == row_id]
    assert len(matches) == 1
    matches[0].update(updates)
    _write_csv(path, rows)


def _summary_row(rows: list[dict[str, str]], summary_id: str) -> dict[str, str]:
    matches = [row for row in rows if row["summary_id"] == summary_id]
    assert len(matches) == 1
    return matches[0]


def _check(result: dict[str, Any], check_id: str) -> dict[str, Any]:
    matches = [item for item in result["checks"] if item["check_id"] == check_id]
    assert len(matches) == 1
    return matches[0]


def _output_bytes(output_dir: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(output_dir.iterdir())
        if path.is_file()
    }


def test_customer_concentration_preparation_emits_exact_bounded_outputs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"

    result = PREPARER.prepare_customer_concentration_case(CASE_PATH, output_dir)

    assert result["status"] == "passed"
    assert result["publication_status"] == "withheld"
    assert result["report_ready"] is False
    assert result["counts"] == {
        "fact_rows": 18,
        "control_fact_rows": 5,
        "unique_fact_ids": 18,
        "unique_natural_keys": 18,
        "unique_control_ids": 5,
        "unique_control_natural_keys": 5,
        "summary_results": 16,
        "exception_rows": 0,
        "errors": 0,
    }
    assert all(check["status"] == "passed" for check in result["checks"])
    assert result["authority_boundary"] == {
        "source": "receipt_and_review_only",
        "semantic": "reviewed_boundary_only",
    }
    assert result["claim_abstention"] == {
        "status": "passed",
        "forbidden_claim_ids": [
            "alias_to_customer_name_mapping",
            *FORBIDDEN_CLAIMS,
        ],
        "offending_input_claim_ids": [],
        "emitted_forbidden_claim_ids": [],
    }

    summary = _read_csv(output_dir / "customer_concentration_summary.csv")
    assert len(summary) == 16
    assert (
        _summary_row(summary, "udc_2025_disclosed_top_three_revenue_share")["value"]
        == "79"
    )
    assert (
        _summary_row(summary, "udc_2024_disclosed_top_three_revenue_share")["value"]
        == "82"
    )
    assert (
        _summary_row(summary, "udc_2023_disclosed_top_three_revenue_share")["value"]
        == "76"
    )
    assert (
        _summary_row(summary, "udc_2025_disclosed_accounts_receivable_subtotal")[
            "value"
        ]
        == "103481"
    )
    assert (
        _summary_row(summary, "udc_2024_disclosed_accounts_receivable_subtotal")[
            "value"
        ]
        == "76908"
    )
    assert (
        _summary_row(summary, "udc_2025_accounts_receivable_coverage_percent")["value"]
        == "86.267955"
    )
    assert (
        _summary_row(summary, "udc_2024_accounts_receivable_coverage_percent")["value"]
        == "67.672110"
    )
    unavailable = _summary_row(summary, "udc_2023_accounts_receivable_coverage_percent")
    assert unavailable["value"] == ""
    assert unavailable["availability_status"] == "unavailable"
    assert result["availability_results"] == [
        {
            "summary_id": "udc_2023_accounts_receivable_coverage_percent",
            "fiscal_year": "2023",
            "metric_id": "accounts_receivable_coverage_percent",
            "status": "unavailable",
            "reason": (
                "The frozen source-control set contains no 2023 total "
                "accounts-receivable denominator."
            ),
        }
    ]
    hhi_rows = [
        row for row in summary if row["metric_id"] == "reported_share_hhi_contribution"
    ]
    assert {row["fiscal_year"]: row["value"] for row in hhi_rows} == {
        "2025": "2515",
        "2024": "2634",
        "2023": "2114",
    }
    assert {row["metric_id"] for row in summary}.isdisjoint(
        {"full_hhi", "hhi_lower_bound"}
    )
    assert _read_csv(output_dir / "exceptions.csv") == []

    case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    source = case["sources"][0]
    assert {
        "source_id": source["source_id"],
        "accession": source["accession"],
        "filed_date": source["filed_date"],
        "byte_count": source["byte_count"],
        "sha256": source["sha256"],
    } == EXPECTED_SOURCE_RECEIPT
    manifest = json.loads(
        (output_dir / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["preparation_status"] == "passed"
    assert manifest["publication_status"] == "withheld"
    assert manifest["report_ready"] is False
    assert [item["artifact_id"] for item in manifest["inputs"]] == [
        "exact_control_facts",
        "exact_extracted_facts",
    ]
    assert _output_bytes(output_dir) == _output_bytes(EXPECTED_ROOT)


def test_customer_concentration_fixture_and_outputs_are_hash_pinned() -> None:
    actual = {
        "case.json": _sha256(CASE_PATH),
        "exact_control_facts.csv": _sha256(CONTROL_FACTS_PATH),
        "exact_extracted_facts.csv": _sha256(FACTS_PATH),
        **{
            path.name: _sha256(path)
            for path in EXPECTED_ROOT.iterdir()
            if path.is_file()
        },
    }

    assert actual == EXPECTED_FILE_HASHES


@pytest.mark.parametrize("identifier_field", ["case_id", "source_id"])
def test_customer_concentration_rejects_noncanonical_padded_identifier(
    tmp_path: Path,
    identifier_field: str,
) -> None:
    _, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    if identifier_field == "case_id":
        case["case_id"] = " padded-case "
    else:
        case["sources"][0]["source_id"] = " padded-source "
    _write_json(case_path, case)
    output_dir = tmp_path / "prepared"

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="must not contain leading or trailing whitespace",
    ):
        PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_customer_concentration_preparation_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = PREPARER.prepare_customer_concentration_case(CASE_PATH, first_dir)
    second = PREPARER.prepare_customer_concentration_case(CASE_PATH, second_dir)

    assert first["status"] == second["status"] == "passed"
    assert _output_bytes(first_dir) == _output_bytes(second_dir)


def test_customer_concentration_wrong_share_fails_and_removes_stale_success(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    _mutate_row(
        facts_path,
        row_id_field="fact_id",
        row_id="udc_2025_a_revenue_share",
        updates={"value": "44"},
    )
    _reseal_case_asset(case_path, "exact_extracted_facts")
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    result = PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert result["status"] == "failed"
    assert _check(result, "revenue_share_subtotals")["status"] == "failed"
    assert _check(result, "reported_share_hhi_contribution")["status"] == "failed"
    assert {path.name for path in output_dir.iterdir()} == {
        "exceptions.csv",
        "reconciliation.json",
    }
    assert len(_read_csv(output_dir / "exceptions.csv")) == result["counts"]["errors"]


def test_customer_concentration_source_control_mutation_fails_provenance_checks(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    controls_path = _case_asset(case_path, "exact_control_facts")
    _mutate_row(
        controls_path,
        row_id_field="control_id",
        row_id="udc_2025_total_accounts_receivable",
        updates={"value": "100000"},
    )
    _reseal_case_asset(case_path, "exact_control_facts")
    output_dir = tmp_path / "prepared"

    result = PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert result["status"] == "failed"
    assert _check(result, "control_values")["status"] == "failed"
    assert _check(result, "accounts_receivable_subtotals")["status"] == "failed"
    assert _check(result, "accounts_receivable_coverage")["status"] == "failed"
    assert {path.name for path in output_dir.iterdir()} == {
        "exceptions.csv",
        "reconciliation.json",
    }


def test_customer_concentration_zero_denominator_emits_failure_artifacts(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    controls_path = _case_asset(case_path, "exact_control_facts")
    _mutate_row(
        controls_path,
        row_id_field="control_id",
        row_id="udc_2025_total_accounts_receivable",
        updates={"value": "0"},
    )
    _reseal_case_asset(case_path, "exact_control_facts")
    output_dir = tmp_path / "prepared"

    result = PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert result["status"] == "failed"
    assert _check(result, "accounts_receivable_coverage")["status"] == "failed"
    assert any(
        error["code"] == "invalid_total_accounts_receivable_denominator"
        for error in result["errors"]
    )
    assert {path.name for path in output_dir.iterdir()} == {
        "exceptions.csv",
        "reconciliation.json",
    }


@pytest.mark.parametrize("forbidden_claim", FORBIDDEN_CLAIMS)
def test_customer_concentration_rejects_forbidden_metric_claims(
    tmp_path: Path,
    forbidden_claim: str,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    _mutate_row(
        facts_path,
        row_id_field="fact_id",
        row_id="udc_2025_a_revenue_share",
        updates={
            "fact_id": f"udc_2025_a_{forbidden_claim}",
            "metric_id": forbidden_claim,
        },
    )
    _reseal_case_asset(case_path, "exact_extracted_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert result["claim_abstention"]["status"] == "failed"
    assert forbidden_claim in result["claim_abstention"]["offending_input_claim_ids"]
    assert _check(result, "claim_abstention")["status"] == "failed"


def test_customer_concentration_rejects_unknown_alias_without_identity_inference(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    _mutate_row(
        facts_path,
        row_id_field="fact_id",
        row_id="udc_2025_a_revenue_share",
        updates={
            "fact_id": "udc_2025_d_revenue_share",
            "customer_alias": "D",
        },
    )
    _reseal_case_asset(case_path, "exact_extracted_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert result["claim_abstention"]["status"] == "passed"
    assert _check(result, "claim_abstention")["status"] == "passed"
    assert "unsupported_customer_alias" in {error["code"] for error in result["errors"]}
    assert "alias_identity_claim_forbidden" not in {
        error["code"] for error in result["errors"]
    }


def test_customer_concentration_rejects_explicit_alias_identity_claim(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["declared_input_claim_ids"] = ["alias_to_customer_name_mapping"]
    _write_json(case_path, case)

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert result["claim_abstention"]["status"] == "failed"
    assert result["claim_abstention"]["offending_input_claim_ids"] == [
        "alias_to_customer_name_mapping"
    ]
    assert "forbidden_declared_input_claim" in {
        error["code"] for error in result["errors"]
    }


def test_customer_concentration_rejects_duplicate_fact(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    rows = _read_csv(facts_path)
    rows.append(dict(rows[0]))
    _write_csv(facts_path, rows)
    _reseal_case_asset(case_path, "exact_extracted_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, "duplicate_control")["status"] == "failed"
    assert any(error["code"] == "duplicate_fact_id" for error in result["errors"])


def test_customer_concentration_rejects_duplicate_control_fact(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    controls_path = _case_asset(case_path, "exact_control_facts")
    rows = _read_csv(controls_path)
    rows.append(dict(rows[0]))
    _write_csv(controls_path, rows)
    _reseal_case_asset(case_path, "exact_control_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, "duplicate_control")["status"] == "failed"
    assert any(error["code"] == "duplicate_control_id" for error in result["errors"])


def test_customer_concentration_rejects_omitted_fact(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    rows = [
        row
        for row in _read_csv(facts_path)
        if row["fact_id"] != "udc_2025_a_revenue_share"
    ]
    _write_csv(facts_path, rows)
    _reseal_case_asset(case_path, "exact_extracted_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, "exact_fact_set")["status"] == "failed"
    assert any(error["code"] == "missing_fact" for error in result["errors"])
    assert {path.name for path in (tmp_path / "prepared").iterdir()} == {
        "exceptions.csv",
        "reconciliation.json",
    }


def test_customer_concentration_rejects_omitted_control_fact(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    controls_path = _case_asset(case_path, "exact_control_facts")
    rows = [
        row
        for row in _read_csv(controls_path)
        if row["control_id"] != "udc_2025_total_accounts_receivable"
    ]
    _write_csv(controls_path, rows)
    _reseal_case_asset(case_path, "exact_control_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, "exact_fact_set")["status"] == "failed"
    assert any(error["code"] == "missing_control_fact" for error in result["errors"])


def test_customer_concentration_rejects_extra_fact(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    rows = _read_csv(facts_path)
    extra = dict(rows[0])
    extra.update(
        {
            "fact_id": "udc_2025_d_revenue_share",
            "customer_alias": "D",
        }
    )
    rows.append(extra)
    _write_csv(facts_path, rows)
    _reseal_case_asset(case_path, "exact_extracted_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, "exact_fact_set")["status"] == "failed"
    assert any(error["code"] == "unexpected_fact" for error in result["errors"])
    assert {path.name for path in (tmp_path / "prepared").iterdir()} == {
        "exceptions.csv",
        "reconciliation.json",
    }


def test_customer_concentration_rejects_extra_control_fact(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    controls_path = _case_asset(case_path, "exact_control_facts")
    rows = _read_csv(controls_path)
    extra = dict(rows[-1])
    extra.update(
        {
            "control_id": "udc_2023_total_accounts_receivable",
            "fiscal_year": "2023",
        }
    )
    rows.append(extra)
    _write_csv(controls_path, rows)
    _reseal_case_asset(case_path, "exact_control_facts")

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, "exact_fact_set")["status"] == "failed"
    assert any(error["code"] == "unexpected_control_fact" for error in result["errors"])


@pytest.mark.parametrize(
    ("file_id", "row_id_field", "row_id", "updates", "check_id", "error_code"),
    [
        (
            "exact_extracted_facts",
            "fact_id",
            "udc_2025_a_revenue_share",
            {"unit": "ratio"},
            "unit_increment_contract",
            "unit_mismatch",
        ),
        (
            "exact_extracted_facts",
            "fact_id",
            "udc_2025_a_revenue_share",
            {"reported_increment": "0.1"},
            "unit_increment_contract",
            "reported_increment_mismatch",
        ),
        (
            "exact_extracted_facts",
            "fact_id",
            "udc_2025_a_revenue_share",
            {"source_id": "unreviewed_source"},
            "source_contract",
            "unknown_source",
        ),
        (
            "exact_extracted_facts",
            "fact_id",
            "udc_2025_a_revenue_share",
            {"source_locator": "unreviewed locator"},
            "source_contract",
            "source_locator_mismatch",
        ),
        (
            "exact_control_facts",
            "control_id",
            "udc_2025_total_accounts_receivable",
            {"unit": "USD"},
            "unit_increment_contract",
            "control_unit_mismatch",
        ),
        (
            "exact_control_facts",
            "control_id",
            "udc_2025_total_accounts_receivable",
            {"reported_increment": "1000"},
            "unit_increment_contract",
            "control_increment_mismatch",
        ),
        (
            "exact_control_facts",
            "control_id",
            "udc_2025_total_accounts_receivable",
            {"source_id": "unreviewed_source"},
            "source_contract",
            "unknown_control_source",
        ),
        (
            "exact_control_facts",
            "control_id",
            "udc_2025_total_accounts_receivable",
            {"source_locator": "unreviewed locator"},
            "source_contract",
            "control_source_locator_mismatch",
        ),
    ],
)
def test_customer_concentration_adversarial_fact_contract_changes_fail_closed(
    tmp_path: Path,
    file_id: str,
    row_id_field: str,
    row_id: str,
    updates: dict[str, str],
    check_id: str,
    error_code: str,
) -> None:
    _, case_path = _copy_case(tmp_path)
    asset_path = _case_asset(case_path, file_id)
    _mutate_row(
        asset_path,
        row_id_field=row_id_field,
        row_id=row_id,
        updates=updates,
    )
    _reseal_case_asset(case_path, file_id)

    result = PREPARER.prepare_customer_concentration_case(
        case_path,
        tmp_path / "prepared",
    )

    assert result["status"] == "failed"
    assert _check(result, check_id)["status"] == "failed"
    assert any(error["code"] == error_code for error in result["errors"])
    assert {path.name for path in (tmp_path / "prepared").iterdir()} == {
        "exceptions.csv",
        "reconciliation.json",
    }


def test_customer_concentration_rejects_unsealed_input_change(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    facts_path.write_bytes(facts_path.read_bytes() + b"\n")
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="fact-file SHA-256 does not match",
    ):
        PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_customer_concentration_rejects_surplus_customer_name_column(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    facts_path = _case_asset(case_path, "exact_extracted_facts")
    rows = _read_csv(facts_path)
    fieldnames = [*rows[0], "customer_name"]
    with facts_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows({**row, "customer_name": ""} for row in rows)
    _reseal_case_asset(case_path, "exact_extracted_facts")
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="columns must equal",
    ):
        PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_customer_concentration_rejects_weakened_claim_boundary(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["reviewed_boundary"]["forbidden_claim_ids"].remove("hhi_lower_bound")
    _write_json(case_path, case)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="forbidden claim boundary changed",
    ):
        PREPARER.prepare_customer_concentration_case(
            case_path,
            tmp_path / "prepared",
        )


def test_customer_concentration_requires_explicit_source_extraction_review(
    tmp_path: Path,
) -> None:
    _, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["source_extraction_review"]["status"] = "draft"
    _write_json(case_path, case)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="source_extraction_review.status must be reviewed",
    ):
        PREPARER.prepare_customer_concentration_case(
            case_path,
            tmp_path / "prepared",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("publication_status", "emitted", "publication must remain withheld"),
        ("report_ready", True, "report_ready must remain false"),
    ],
)
def test_customer_concentration_rejects_publication_boundary_escalation(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    _, case_path = _copy_case(tmp_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["reviewed_boundary"][field] = value
    _write_json(case_path, case)
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)

    with pytest.raises(KERNEL.ContractValidationError, match=message):
        PREPARER.prepare_customer_concentration_case(case_path, output_dir)

    assert list(output_dir.iterdir()) == []


def test_customer_concentration_audit_adapter_emits_valid_bounded_envelope() -> None:
    envelope = AUDIT_ADAPTER.build_customer_concentration_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )

    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(envelope)
    assert envelope["case"] == {
        "case_id": "udc-fy2025-customer-concentration",
        "case_kind": "reviewed_public_customer_concentration_benchmark",
        "source_schema_version": ("clara.customer_concentration_preparation_case.v1"),
        "case_artifact_ref": "case_contract",
    }
    assert {
        status_id: status["status"]
        for status_id, status in envelope["statuses"].items()
    } == {
        "validation": "passed",
        "preparation": "passed",
        "reconciliation": "passed",
        "semantic": "not_assessed",
        "source": "receipt_only",
        "downstream": "not_assessed",
        "publication": "withheld",
    }
    assert envelope["report_ready"] is False
    assert envelope["remote_sources"][0]["source_id"] == "udc_fy2025_10k"
    assert envelope["remote_sources"][0]["receipt_scope"] == ("declared_remote_receipt")
    assert {item["artifact_id"] for item in envelope["local_artifacts"]}.issuperset(
        {"exact_control_facts", "exact_extracted_facts", "exceptions"}
    )
    assert {item["decision_id"] for item in envelope["reviewed_decisions"]} == {
        "claim_boundary_review",
        "source_extraction_review",
    }
    coverage_check = next(
        check
        for check in envelope["reconciliation"]["checks"]
        if check["check_id"] == "accounts_receivable_coverage"
    )
    assert {
        item["name"]: item["value"] for item in coverage_check["numeric_evidence"]
    } == {
        "udc_2024_accounts_receivable_coverage_percent": "67.67211",
        "udc_2025_accounts_receivable_coverage_percent": "86.267955",
    }
    assert coverage_check["details"]["availability_results"][0]["status"] == (
        "unavailable"
    )


def test_customer_concentration_audit_envelope_is_byte_deterministic() -> None:
    first = AUDIT_ADAPTER.build_customer_concentration_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )
    second = AUDIT_ADAPTER.build_customer_concentration_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )
    first_bytes = (
        json.dumps(first, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    second_bytes = (
        json.dumps(second, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    assert first_bytes == second_bytes
    assert hashlib.sha256(first_bytes).hexdigest() == EXPECTED_ENVELOPE_SHA256


def test_customer_concentration_preparation_rejects_unregistered_output_entry(
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
        PREPARER.prepare_customer_concentration_case(CASE_PATH, output_dir)

    assert not stale_success.exists()
    assert unregistered.read_text(encoding="utf-8") == "not a producer artifact\n"


def test_customer_concentration_audit_adapter_rejects_tampered_output(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, output_dir)
    summary_path = output_dir / "customer_concentration_summary.csv"
    summary_path.write_bytes(summary_path.read_bytes() + b"\n")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="does not match deterministic replay",
    ):
        AUDIT_ADAPTER.build_customer_concentration_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=CASE_PATH,
            prepared_output_dir=output_dir,
        )


def test_customer_concentration_audit_adapter_rejects_unregistered_output_entry(
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
        AUDIT_ADAPTER.build_customer_concentration_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=CASE_PATH,
            prepared_output_dir=output_dir,
        )


def test_customer_concentration_audit_cli_removes_stale_output_on_failure(
    tmp_path: Path,
) -> None:
    prepared_output = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, prepared_output)
    summary_path = prepared_output / "customer_concentration_summary.csv"
    summary_path.write_bytes(summary_path.read_bytes() + b"\n")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text('{"stale":"passed"}\n', encoding="utf-8")

    exit_code = AUDIT_ADAPTER.main(
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


def test_customer_concentration_audit_adapter_preserves_failed_run() -> None:
    with TemporaryDirectory(prefix=".m5a-failed-", dir=CLARA_ROOT) as raw_dir:
        run_root = Path(raw_dir)
        case_root = run_root / "case"
        shutil.copytree(CASE_ROOT, case_root)
        case_path = case_root / "case.json"
        facts_path = _case_asset(case_path, "exact_extracted_facts")
        _mutate_row(
            facts_path,
            row_id_field="fact_id",
            row_id="udc_2025_a_revenue_share",
            updates={"value": "44"},
        )
        _reseal_case_asset(case_path, "exact_extracted_facts")
        output_dir = run_root / "prepared"
        result = PREPARER.prepare_customer_concentration_case(case_path, output_dir)

        envelope = AUDIT_ADAPTER.build_customer_concentration_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=case_path,
            prepared_output_dir=output_dir,
        )

        assert result["status"] == "failed"
        assert {
            status_id: envelope["statuses"][status_id]["status"]
            for status_id in ("validation", "preparation", "reconciliation")
        } == {
            "validation": "failed",
            "preparation": "failed",
            "reconciliation": "failed",
        }
        assert envelope["statuses"]["publication"]["status"] == "withheld"
        assert envelope["report_ready"] is False
        artifact_ids = {item["artifact_id"] for item in envelope["local_artifacts"]}
        assert "customer_concentration_summary" not in artifact_ids
        assert "prepared_evidence_manifest" not in artifact_ids
        assert {"exceptions", "reconciliation"}.issubset(artifact_ids)
