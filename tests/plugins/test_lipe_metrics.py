"""First-pass denominators and attributed changes, using fictional cases only."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
from lipe_catalog import create_catalog, history, record
from lipe_core import ContractError, read_json
from lipe_metrics import capture_first_pass, main, record_review, report


def fixture(root: Path) -> tuple[Path, dict, dict]:
    path = root / "catalog.sqlite3"
    metadata = create_catalog(path, "fictional-studio", "0.80")
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    for mapping in case["mappings"]:
        mapping["review"]["status"] = "PROPOSED"
    shutil.copy(PLUGIN / "examples/synthetic-registers.txt", root)
    case["catalog_context"] = {
        "catalog_id": metadata["catalog_id"],
        "studio_id": metadata["studio_id"],
    }
    legend = root / "fictional-legend.txt"
    legend.write_text(
        "SYNTHETIC ONLY. V22: taxable sales; A22: purchases.", encoding="utf-8"
    )
    source = {
        "source_id": "legend",
        "path": legend.name,
        "sha256": hashlib.sha256(legend.read_bytes()).hexdigest(),
        "visibility": "PUBLIC",
    }
    case["sources"].append(
        {key: source[key] for key in ("source_id", "path", "sha256")}
    )
    entry = {
        "schema_version": "lipe.catalog.entry.v1",
        "entry_id": "fictional-sales",
        "scope": "STUDIO",
        "client_id": None,
        "software": case["software"],
        "side": "SALES",
        "code": "V22",
        "description": "Fictional fixture",
        "tax_class": {
            "treatment": "SALE_TAXABLE",
            "vat_rate": "22.00",
            "vat_nature": None,
            "deductibility": {"mode": "CASE_SPECIFIC", "percent": None},
            "mechanism": None,
            "counterparty_regime": None,
            "legal_basis": None,
        },
        "confidence": {"value": "0.90", "basis": "Fictional fixture"},
        "valid_from": "2026-01-01",
        "valid_until": None,
        "sources": [source],
        "evidence": [
            {
                "source_id": "legend",
                "page": 1,
                "quote": legend.read_text(encoding="utf-8"),
            }
        ],
        "review": case["scope_review"],
        "curator_review": None,
        "disclosure_review": None,
    }
    record(path, entry, root, expected_head=history(path)["head_hash"])
    return path, case, entry


def capture(path: Path, case: dict, proposals: list[dict] | None = None) -> dict:
    return capture_first_pass(
        path,
        case,
        path.parent,
        {
            "timing_declaration": "BEFORE_PROFESSIONAL_REVIEW",
            "model_proposals": proposals or [],
        },
        expected_head=history(path)["head_hash"],
    )


def decision(
    first: dict, entry: dict, *, side: str = "SALES", outcome: str = "CONFIRMED"
) -> dict:
    unit = next(item for item in first["event"]["units"] if item["side"] == side)
    return {
        "unit_id": unit["unit_id"],
        "outcome": outcome,
        "tax_class": copy.deepcopy(entry["tax_class"]),
        "sources": entry["sources"],
        "evidence": entry["evidence"],
        "review": entry["review"],
    }


def review(path: Path, value: dict, **kwargs: object) -> dict:
    return record_review(
        path, value, path.parent, expected_head=history(path)["head_hash"], **kwargs
    )


def test_every_observed_code_is_in_denominator_even_without_proposal(
    tmp_path: Path,
) -> None:
    path, case, _ = fixture(tmp_path)
    capture(path, case)

    result = report(path)["cohorts"][0]

    assert result["units"] == 2
    assert result["recognition"] == {
        "numerator": 1,
        "denominator": 2,
        "percent": "50.00",
    }
    assert result["professional_class_change"]["percent"] is None
    assert result["currently_unresolved"] == 2


def test_repeated_capture_and_new_case_id_do_not_reset_first_pass(
    tmp_path: Path,
) -> None:
    path, case, _ = fixture(tmp_path)
    capture(path, case)
    case["case_id"] = "resumed-corrected-run"
    previous = history(path)["head_hash"]

    result = capture(path, case)

    assert result["status"] == "ALREADY_RECORDED"
    assert result["previously_recorded_units"] == 2
    assert history(path)["head_hash"] == previous


def test_first_resolved_correction_stays_counted_after_later_reversal(
    tmp_path: Path,
) -> None:
    path, case, entry = fixture(tmp_path)
    first = capture(path, case)
    value = decision(first, entry, outcome="CORRECTED")
    value["tax_class"]["treatment"] = "SALE_EXCLUDED"
    changed = review(path, value)
    restored = decision(first, entry)
    review(path, restored, supersedes=changed["event_hash"])

    result = report(path)["cohorts"][0]

    assert result["professional_class_change"] == {
        "numerator": 1,
        "denominator": 1,
        "percent": "100.00",
    }
    assert result["first_resolution_coverage"]["percent"] == "50.00"
    assert result["currently_unresolved"] == 1


def test_unresolved_review_is_not_confirmation_or_zero_correction(
    tmp_path: Path,
) -> None:
    path, case, entry = fixture(tmp_path)
    first = capture(path, case)
    value = decision(first, entry, outcome="UNRESOLVED")
    value["tax_class"] = None
    review(path, value)

    result = report(path)["cohorts"][0]

    assert result["professional_class_change"]["denominator"] == 0
    assert result["professional_class_change"]["percent"] is None
    assert result["first_resolution_coverage"]["numerator"] == 0


def test_resolution_of_unknown_code_is_not_a_corrected_prediction(
    tmp_path: Path,
) -> None:
    path, case, entry = fixture(tmp_path)
    first = capture(path, case)
    value = decision(first, entry, side="PURCHASES", outcome="RESOLVED_NEW")
    value["tax_class"]["treatment"] = "PURCHASE"
    review(path, value)

    result = report(path)["cohorts"][0]

    assert result["resolved_without_initial_proposal"] == 1
    assert result["professional_class_change"]["denominator"] == 0


@pytest.mark.parametrize("confidence,recognized", [("0.79", 1), ("0.80", 2)])
def test_model_proposal_measures_declared_cutoff_separately_from_catalog(
    tmp_path: Path, confidence: str, recognized: int
) -> None:
    path, case, entry = fixture(tmp_path)
    proposal = {
        key: copy.deepcopy(entry[key])
        for key in ("side", "code", "tax_class", "confidence", "evidence")
    }
    proposal.update(side="PURCHASES", code="A22")
    proposal["tax_class"]["treatment"] = "PURCHASE"
    proposal["confidence"]["value"] = confidence
    capture(path, case, [proposal])

    result = report(path)["cohorts"][0]

    assert result["recognition"]["numerator"] == recognized
    assert result["catalog_availability"]["numerator"] == 1


def test_real_and_synthetic_observations_are_never_pooled(tmp_path: Path) -> None:
    path, case, _ = fixture(tmp_path)
    capture(path, case)
    case["data_origin"] = "REAL"
    capture(path, case)

    result = report(path)

    assert [item["data_origin"] for item in result["cohorts"]] == ["REAL", "SYNTHETIC"]
    assert [item["units"] for item in result["cohorts"]] == [2, 2]
    assert result["identity_and_timing_authenticated"] is False


def test_interior_quarter_class_change_is_not_first_pass_catalog_recognition(
    tmp_path: Path,
) -> None:
    path, case, entry = fixture(tmp_path)
    alternative = copy.deepcopy(entry)
    alternative.update(
        entry_id="temporary-conflict", valid_from="2026-05-01", valid_until="2026-05-31"
    )
    alternative["tax_class"]["treatment"] = "SALE_EXCLUDED"
    record(path, alternative, tmp_path, expected_head=history(path)["head_hash"])
    capture(path, case)

    result = report(path)["cohorts"][0]

    assert result["recognition"]["numerator"] == 0


def test_high_confidence_model_proposal_does_not_hide_catalog_conflict(
    tmp_path: Path,
) -> None:
    path, case, entry = fixture(tmp_path)
    alternative = copy.deepcopy(entry)
    alternative["entry_id"] = "conflicting-class"
    alternative["tax_class"]["treatment"] = "SALE_EXCLUDED"
    record(path, alternative, tmp_path, expected_head=history(path)["head_hash"])
    proposal = {
        key: copy.deepcopy(entry[key])
        for key in ("side", "code", "tax_class", "confidence", "evidence")
    }
    capture(path, case, [proposal])

    result = report(path)["cohorts"][0]

    assert result["recognition"]["numerator"] == 0
    assert result["catalog_availability"]["numerator"] == 0


@pytest.mark.parametrize("change", ["label", "unit", "class", "source"])
def test_inconsistent_or_unbound_professional_review_is_rejected(
    tmp_path: Path, change: str
) -> None:
    path, case, entry = fixture(tmp_path)
    first = capture(path, case)
    value = decision(first, entry)
    if change == "label":
        value["outcome"] = "CORRECTED"
    elif change == "unit":
        value["unit_id"] = "f" * 64
    elif change == "class":
        value["tax_class"]["treatment"] = "PURCHASE"
    else:
        value["sources"][0]["sha256"] = "f" * 64

    with pytest.raises(ContractError):
        review(path, value)


def test_cli_report_writes_once_without_client_identifiers(tmp_path: Path) -> None:
    path, case, _ = fixture(tmp_path)
    capture(path, case)
    output = tmp_path / "report.json"

    status = main(["report", "--catalog", str(path), "--output", str(output)])

    assert status == 0
    assert case["client_id"] not in output.read_text(encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8"))["cohorts"][0]["units"] == 2


def test_stale_head_cannot_rewrite_first_pass(tmp_path: Path) -> None:
    path, case, _ = fixture(tmp_path)
    with pytest.raises(ContractError, match="changed"):
        capture_first_pass(
            path,
            case,
            tmp_path,
            {"timing_declaration": "BEFORE_PROFESSIONAL_REVIEW", "model_proposals": []},
            expected_head="f" * 64,
        )


def test_already_confirmed_case_cannot_be_claimed_as_new_first_pass(
    tmp_path: Path,
) -> None:
    path, case, _ = fixture(tmp_path)
    case["mappings"][0]["review"]["status"] = "CONFIRMED"

    with pytest.raises(ContractError, match="before confirming"):
        capture(path, case)


def test_real_cli_measurement_requires_archive_identity_before_receipt(
    tmp_path: Path,
) -> None:
    path, case, _ = fixture(tmp_path)
    case["data_origin"] = "REAL"
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(case), encoding="utf-8")
    proposals = tmp_path / "proposals.json"
    proposals.write_text(
        json.dumps(
            {"timing_declaration": "BEFORE_PROFESSIONAL_REVIEW", "model_proposals": []}
        ),
        encoding="utf-8",
    )
    output = tmp_path / "receipt.json"

    with pytest.raises(ContractError, match="Archive"):
        main(
            [
                "first-pass",
                "--catalog",
                str(path),
                "--case",
                str(case_path),
                "--proposals",
                str(proposals),
                "--source-root",
                str(tmp_path),
                "--expected-head",
                history(path)["head_hash"],
                "--output",
                str(output),
            ]
        )
    assert not output.exists()


def test_missing_original_evidence_blocks_metrics_report(tmp_path: Path) -> None:
    path, case, _ = fixture(tmp_path)
    capture(path, case)
    next(tmp_path.glob("catalog.sqlite3.sources/*")).unlink()

    with pytest.raises(ContractError, match="missing or changed"):
        report(path)


@pytest.mark.parametrize("invalid", ["deduction", "rate", "unquoted_code", "duplicate"])
def test_model_proposals_require_consistent_classes_and_exact_evidence(
    tmp_path: Path, invalid: str
) -> None:
    path, case, entry = fixture(tmp_path)
    proposal = {
        key: copy.deepcopy(entry[key])
        for key in ("side", "code", "tax_class", "confidence", "evidence")
    }
    proposals = [proposal]
    if invalid == "deduction":
        proposal["tax_class"]["deductibility"] = {"mode": "FULL", "percent": "50.00"}
    elif invalid == "rate":
        proposal["tax_class"]["vat_rate"] = "100.99"
    elif invalid == "unquoted_code":
        proposal["evidence"] = [case["registers"][0]["rows"][0]["evidence"]]
    else:
        proposals.append(copy.deepcopy(proposal))

    with pytest.raises(ContractError):
        capture(path, case, proposals)


def test_relabelling_quarter_without_matching_case_periods_is_rejected(
    tmp_path: Path,
) -> None:
    path, case, _ = fixture(tmp_path)
    capture(path, case)
    case["quarter"] = 3
    with pytest.raises(ContractError, match="complete quarter"):
        capture(path, case)
