"""Independent LIPE examples and failure-boundary regressions, all synthetic."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
from lipe import extract, main, save_result
from lipe_core import ContractError, calculate, digest, money, read_json, validate
from lipe_xml import build_test_xml

XLSX_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def case_data() -> dict:
    """Return a fresh explicitly synthetic case."""
    return read_json(PLUGIN / "examples/synthetic-case.json")


def prepare(case: dict, root: Path) -> Path:
    """Write invented evidence matching test inputs; never compute an oracle."""
    lines = []
    source_id = "synthetic-source"

    def ref(quote: str) -> dict:
        lines.append(quote)
        return {"source_id": source_id, "page": 1, "quote": quote}

    if case["opening"]:
        opening = case["opening"]
        opening["evidence"] = ref(
            f"Opening: credit {opening['credit']}; small debit {opening['small_debit']}."
        )
    for register in case["registers"]:
        register["evidence"] = ref(
            f"TOTAL {register['register_id']}: {register['printed_base']} {register['printed_tax']}."
        )
        for row in register["rows"]:
            row["evidence"] = ref(f"ROW {row['row_id']}: {row['base']} {row['tax']}.")
    for module in case["modules"]:
        module["evidence"] = ref(
            f"ADJUSTMENTS {module['period']}: confirmed synthetic values."
        )
    for document in case["liquidations"]:
        document["evidence"] = ref(f"LIQUIDATION {document['period']}: complete.")
        for section in document["sections"]:
            for row in section["rows"]:
                row["evidence"] = ref(
                    f"LIQUIDATION {document['period']} {section['side']} "
                    f"{section['tax_basis']} {row['code']}: {row['base']} {row['tax']}."
                )
    path = root / "evidence.txt"
    path.write_text("\n".join(lines))
    case["sources"] = [
        {
            "source_id": source_id,
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    ]
    return root


def amounts(
    case: dict, period: int, side: str, base: str, tax: str, deductible: str
) -> None:
    register = next(
        r for r in case["registers"] if r["period"] == period and r["side"] == side
    )
    register.update(printed_base=base, printed_tax=tax)
    register["rows"][0].update(base=base, tax=tax, deductible_tax=deductible)


def quarterly(quarter: int = 2, regime: str = "QUARTERLY_OPTION") -> dict:
    case = case_data()
    case.update(regime=regime, quarter=quarter)
    case["modules"] = [case["modules"][0]]
    case["modules"][0]["period"] = quarter
    case["liquidations"] = [case["liquidations"][0]]
    case["liquidations"][0]["period"] = quarter
    case["registers"] = case["registers"][:2]
    for register in case["registers"]:
        register["period"] = quarter
        register["rows"][0].update(
            base_period=quarter, tax_period=quarter, deduction_period=quarter
        )
    return case


def test_monthly_fixture_has_independently_known_vp_values() -> None:
    result = calculate(case_data(), PLUGIN / "examples")
    assert result["status"] == "DRAFT_FOR_REVIEW"
    assert result["modules"][0]["rows"] == {
        "vp2": "1000.00",
        "vp3": "500.00",
        "vp4": "220.00",
        "vp5": "110.00",
        "vp6_debit": "110.00",
        "vp6_credit": "0.00",
        "vp7": "0.00",
        "vp8": "0.00",
        "vp9": "0.00",
        "vp10": "0.00",
        "vp11": "0.00",
        "vp12": "0.00",
        "vp13": "0.00",
        "vp14_debit": "110.00",
        "vp14_credit": "0.00",
    }
    assert [m["payment_status"] for m in result["modules"]] == ["MATCH"] * 3


def test_per_code_comparison_exposes_offsetting_errors(tmp_path: Path) -> None:
    case = case_data()
    case["liquidations"][0]["sections"][0]["rows"][0]["tax"] = "230.00"
    case["liquidations"][0]["sections"][1]["rows"][0]["tax"] = "120.00"
    result = calculate(case, prepare(case, tmp_path))
    assert result["reconciliation"][0]["tax_difference"] == "-10.00"
    assert result["reconciliation"][1]["tax_difference"] == "-10.00"
    assert result["modules"][0]["rows"]["vp6_debit"] == "110.00"
    assert [f["code"] for f in result["findings"]] == [
        "CODE_LIQUIDATION_DIFFERENCE",
        "CODE_LIQUIDATION_DIFFERENCE",
    ]


@pytest.mark.parametrize(
    "tax_basis,expected",
    [("RECORDED", "110.00"), ("DEDUCTIBLE", "44.00"), ("OUTPUT", "0.00")],
)
def test_liquidation_basis_distinguishes_recorded_and_deductible_tax(
    tmp_path: Path, tax_basis: str, expected: str
) -> None:
    case = case_data()
    case["registers"][1]["rows"][0]["deductible_tax"] = "44.00"
    section = case["liquidations"][0]["sections"][1]
    section["tax_basis"] = tax_basis
    section["rows"][0]["tax"] = expected
    result = calculate(case, prepare(case, tmp_path))
    assert result["reconciliation"][1]["register_tax"] == expected
    assert result["reconciliation"][1]["status"] == "MATCH"


def test_reconciliation_period_basis_does_not_change_vp_base(tmp_path: Path) -> None:
    case = case_data()
    case["registers"][3]["rows"][0]["deduction_period"] = 4
    case["liquidations"][0]["sections"][1]["base_basis"] = "DEDUCTION"
    result = calculate(case, prepare(case, tmp_path))
    assert result["reconciliation"][1]["register_base"] == "1000.00"
    assert result["reconciliation"][1]["register_tax"] == "220.00"
    assert result["modules"][0]["rows"]["vp3"] == "500.00"


def test_missing_liquidation_line_is_not_zero(tmp_path: Path) -> None:
    case = case_data()
    case["liquidations"][0]["sections"][0]["rows"] = []
    result = calculate(case, prepare(case, tmp_path))
    item = result["reconciliation"][0]
    assert item["status"] == "NOT_REPORTED"
    assert item["liquidation_tax"] is None
    assert item["tax_difference"] is None


def test_liquidation_only_code_has_no_invented_register_amount(tmp_path: Path) -> None:
    case = case_data()
    case["liquidations"][0]["sections"][0]["rows"][0]["code"] = "EXTRA"
    result = calculate(case, prepare(case, tmp_path))
    item = result["reconciliation"][0]
    assert item["status"] == "NO_REGISTER_ROWS"
    assert item["register_tax"] is None
    assert item["tax_difference"] is None


@pytest.mark.parametrize("missing", ["document", "section", "review"])
def test_incomplete_liquidation_blocks_vp(tmp_path: Path, missing: str) -> None:
    case = case_data()
    if missing == "document":
        case["liquidations"].pop(0)
    elif missing == "section":
        case["liquidations"][0]["sections"].pop()
    else:
        case["liquidations"][0]["review"]["status"] = "PROPOSED"
    result = calculate(case, prepare(case, tmp_path))
    assert result["status"] == "BLOCKED"
    assert result["modules"] == []


@pytest.mark.parametrize("duplicate", ["document", "section", "code"])
def test_duplicate_liquidation_records_are_rejected(
    tmp_path: Path, duplicate: str
) -> None:
    case = case_data()
    target = case["liquidations"]
    if duplicate == "section":
        target = target[0]["sections"]
    elif duplicate == "code":
        target = target[0]["sections"][0]["rows"]
    target.append(copy.deepcopy(target[0]))
    with pytest.raises(ContractError, match="Duplicate"):
        calculate(case, prepare(case, tmp_path))


def test_unknown_mapping_does_not_claim_reconciliation_match(tmp_path: Path) -> None:
    case = case_data()
    case["mappings"][0]["review"]["status"] = "PROPOSED"
    result = calculate(case, prepare(case, tmp_path))
    assert result["reconciliation"][0]["register_tax"] is None
    assert result["reconciliation"][0]["status"] == "BASIS_NOT_CONFIRMED"


def workbook_cells(path: Path, sheet: int) -> dict:
    """Inspect saved formulas/caches without needing Excel or another service."""
    with zipfile.ZipFile(path) as archive:
        document = ElementTree.fromstring(
            archive.read(f"xl/worksheets/sheet{sheet}.xml")
        )
    return {cell.attrib["r"]: cell for cell in document.findall(".//s:c", XLSX_NS)}


def test_excel_retains_live_vp_formulas_and_independent_expected_cache(
    tmp_path: Path,
) -> None:
    case = case_data()
    result = calculate(case, PLUGIN / "examples")
    folder = save_result(case, result, tmp_path)
    cells = workbook_cells(folder / "workpaper.xlsx", 2)
    assert cells["C32"].find("s:f", XLSX_NS) is not None
    assert cells["C32"].findtext("s:v", namespaces=XLSX_NS) == "110.0"
    assert cells["D7"].findtext("s:f", namespaces=XLSX_NS) == "C33"
    assert cells["D8"].findtext("s:f", namespaces=XLSX_NS) == "C34"
    assert cells["C36"].findtext("s:v", namespaces=XLSX_NS) == "0"


def test_excel_missing_payment_and_q4_output_do_not_turn_into_zero(
    tmp_path: Path,
) -> None:
    case = quarterly(4)
    case["modules"][0]["principal_paid"] = None
    result = calculate(case, prepare(case, tmp_path))
    folder = save_result(case, result, tmp_path)
    vp = workbook_cells(folder / "workpaper.xlsx", 2)
    f24 = workbook_cells(folder / "workpaper.xlsx", 3)
    assert "C32" not in vp
    assert "D8" not in f24 or f24["D8"].find("s:v", XLSX_NS) is None
    assert not f24["C8"].findtext("s:v", namespaces=XLSX_NS)
    assert not f24["F8"].findtext("s:v", namespaces=XLSX_NS)


def test_excel_treats_external_strings_as_text(tmp_path: Path) -> None:
    case = case_data()
    case["client_id"] = '=HYPERLINK("https://example.invalid", "fake")'
    case["liquidations"][0]["sections"][0]["rows"][0]["code"] = "=1+1"
    result = calculate(case, prepare(case, tmp_path))
    folder = save_result(case, result, tmp_path)
    cells = workbook_cells(folder / "workpaper.xlsx", 1)
    assert cells["D8"].find("s:f", XLSX_NS) is None
    with zipfile.ZipFile(folder / "workpaper.xlsx") as archive:
        assert not any("externalLink" in name for name in archive.namelist())


def test_blocked_excel_contains_no_calculated_tax_values(tmp_path: Path) -> None:
    case = case_data()
    case["opening"] = None
    result = calculate(case, prepare(case, tmp_path))
    folder = save_result(case, result, tmp_path)
    cells = workbook_cells(folder / "workpaper.xlsx", 2)
    assert "C32" not in cells
    assert all(cell.find("s:f", XLSX_NS) is None for cell in cells.values())


def test_vat_deduction_shift_does_not_move_purchase_base(tmp_path: Path) -> None:
    case = case_data()
    case["registers"][3]["rows"][0]["deduction_period"] = 4
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp3"] == "500.00"
    assert result["modules"][0]["rows"]["vp5"] == "220.00"
    assert result["modules"][1]["rows"]["vp3"] == "500.00"
    assert result["modules"][1]["rows"]["vp5"] == "0.00"


def test_partial_reverse_charge_never_invents_full_deduction(tmp_path: Path) -> None:
    case = case_data()
    case["mappings"][1]["treatment"] = "PURCHASE_REVERSE_CHARGE"
    amounts(case, 4, "PURCHASES", "500.00", "110.00", "44.00")
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp4"] == "330.00"
    assert result["modules"][0]["rows"]["vp5"] == "44.00"
    assert result["modules"][0]["rows"]["vp14_debit"] == "286.00"


@pytest.mark.parametrize(
    "treatment,expected_base,expected_vat",
    [("SALE_NO_OUTPUT_VAT", "1000.00", "0.00"), ("SALE_EXCLUDED", "0.00", "0.00")],
)
def test_reviewed_sale_treatments(
    tmp_path: Path, treatment: str, expected_base: str, expected_vat: str
) -> None:
    case = case_data()
    case["mappings"][0]["treatment"] = treatment
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp2"] == expected_base
    assert result["modules"][0]["rows"]["vp4"] == expected_vat


def test_negative_credit_note_reduces_sales_and_vat(tmp_path: Path) -> None:
    case = case_data()
    amounts(case, 4, "SALES", "-100.00", "-22.00", "0.00")
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp2"] == "-100.00"
    assert result["modules"][0]["rows"]["vp6_credit"] == "132.00"
    assert result["modules"][1]["rows"]["vp8"] == "132.00"
    assert result["modules"][1]["rows"]["vp14_credit"] == "22.00"


@pytest.mark.parametrize(
    "regime,interest,debit",
    [("QUARTERLY_OPTION", "1.10", "111.10"), ("QUARTERLY_SPECIAL", "0.00", "110.00")],
)
def test_quarterly_regime_controls_interest(
    tmp_path: Path, regime: str, interest: str, debit: str
) -> None:
    case = quarterly(regime=regime)
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp12"] == interest
    assert result["modules"][0]["rows"]["vp14_debit"] == debit


def test_interest_rounds_half_up_at_cent(tmp_path: Path) -> None:
    case = quarterly()
    amounts(case, 2, "SALES", "1000.00", "220.50", "0.00")
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp12"] == "1.11"
    assert result["modules"][0]["rows"]["vp14_debit"] == "111.61"


def test_q4_option_omits_forbidden_fields_and_uses_quarter_five(tmp_path: Path) -> None:
    case = quarterly(4)
    case["modules"][0].update(vp13="103.29", vp13_method=1)
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["xml_period"] == 5
    assert result["modules"][0]["rows"]["vp12"] is None
    assert result["modules"][0]["rows"]["vp14_debit"] is None
    assert result["modules"][0]["payment_status"] == "NOT_COMPARABLE_ANNUAL_SETTLEMENT"


@pytest.mark.parametrize(
    "defer,paid,expected", [(True, "0.00", "100.00"), (False, "100.00", "0.00")]
)
def test_small_debit_carries_only_when_explicitly_deferred(
    tmp_path: Path, defer: bool, paid: str, expected: str
) -> None:
    case = case_data()
    amounts(case, 4, "SALES", "1000.00", "210.00", "0.00")
    case["modules"][0].update(defer_small_debit=defer, principal_paid=paid)
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp14_debit"] == "100.00"
    assert result["modules"][1]["rows"]["vp7"] == expected


def test_unknown_small_debit_payment_decision_is_not_zero(tmp_path: Path) -> None:
    case = case_data()
    amounts(case, 4, "SALES", "1000.00", "210.00", "0.00")
    case["modules"][0]["defer_small_debit"] = None
    with pytest.raises(ContractError, match="paid or deferred"):
        calculate(case, prepare(case, tmp_path))


def test_opening_credit_and_withheld_credit_use_exact_remainder(tmp_path: Path) -> None:
    case = case_data()
    case["opening"]["credit"] = "200.00"
    case["modules"][0]["credit_withheld"] = "40.00"
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp8"] == "160.00"
    assert result["modules"][0]["rows"]["vp14_credit"] == "50.00"


def test_missing_prior_balance_blocks_instead_of_defaulting_zero(
    tmp_path: Path,
) -> None:
    case = case_data()
    case["opening"] = None
    result = calculate(case, prepare(case, tmp_path))
    assert result["status"] == "BLOCKED"
    assert "OPENING_BALANCE_UNKNOWN" in result["blockers"]
    assert result["modules"] == []


@pytest.mark.parametrize(
    "kind", ["mapping", "scope", "row", "register", "module", "unsupported"]
)
def test_unreviewed_or_unsupported_input_cannot_complete(
    tmp_path: Path, kind: str
) -> None:
    case = case_data()
    if kind == "unsupported":
        case["unsupported_features"] = ["IVA_GROUP"]
    else:
        target = {
            "mapping": case["mappings"][0]["review"],
            "scope": case["scope_review"],
            "row": case["registers"][0]["rows"][0]["review"],
            "register": case["registers"][0]["review"],
            "module": case["modules"][0]["review"],
        }[kind]
        target["status"] = "PROPOSED"
    result = calculate(case, prepare(case, tmp_path))
    assert result["status"] == "BLOCKED"
    assert result["modules"] == []


def test_unmapped_vendor_code_blocks(tmp_path: Path) -> None:
    case = case_data()
    case["registers"][0]["rows"][0]["code"] = "NEW"
    result = calculate(case, prepare(case, tmp_path))
    assert "CODE_NOT_CONFIRMED:SALES:NEW" in result["blockers"]


def test_print_total_mismatch_blocks(tmp_path: Path) -> None:
    case = case_data()
    case["registers"][0]["printed_tax"] = "221.00"
    result = calculate(case, prepare(case, tmp_path))
    assert "REGISTER_TOTAL_MISMATCH:SALES-4" in result["blockers"]


def test_missing_register_in_quarter_blocks(tmp_path: Path) -> None:
    case = case_data()
    case["registers"].pop()
    result = calculate(case, prepare(case, tmp_path))
    assert "REGISTER_COVERAGE_INCOMPLETE:6" in result["blockers"]


@pytest.mark.parametrize(
    "change,error",
    [
        ("source_hash", "Source changed"),
        ("quote", "quotation not found"),
        ("page", "Unknown source or page"),
        ("source_id", "Unknown source or page"),
        ("amount", "absent from source"),
        ("path", "escapes source root"),
        ("deduction", "cannot exceed"),
        ("period", "chronological"),
        ("base_period", "registration period"),
        ("side", "side disagree"),
        ("duplicate_row", "Duplicate row_id"),
        ("duplicate_mapping", "Duplicate code mapping"),
    ],
)
def test_invalid_evidence_and_contract_fail_closed(
    tmp_path: Path, change: str, error: str
) -> None:
    case = case_data()
    prepare(case, tmp_path)
    row = case["registers"][0]["rows"][0]
    if change == "source_hash":
        case["sources"][0]["sha256"] = "0" * 64
    elif change == "quote":
        row["evidence"]["quote"] = "NOT IN SOURCE"
    elif change == "page":
        row["evidence"]["page"] = 2
    elif change == "source_id":
        row["evidence"]["source_id"] = "missing"
    elif change == "amount":
        row["tax"] = "221.00"
    elif change == "path":
        case["sources"][0]["path"] = "../elsewhere.txt"
    elif change == "deduction":
        row["deductible_tax"] = "221.00"
    elif change == "period":
        case["modules"].reverse()
    elif change == "base_period":
        row["base_period"] = 5
    elif change == "side":
        case["mappings"][0]["side"] = "PURCHASES"
    elif change == "duplicate_row":
        case["registers"][0]["rows"].append(copy.deepcopy(row))
    elif change == "duplicate_mapping":
        case["mappings"].append(copy.deepcopy(case["mappings"][0]))
    with pytest.raises(ContractError, match=error):
        calculate(case, tmp_path)


@pytest.mark.parametrize(
    "bad",
    [None, 1.25, "NaN", "Infinity", "1e2", "1,00", "1.001", "100000000000.00", True],
)
def test_money_rejects_ambiguous_or_unbounded_values(bad: object) -> None:
    with pytest.raises(ContractError):
        money(bad)


@pytest.mark.parametrize(
    "payload", ['{"a":1,"a":2}', '{"amount":NaN}', '{"amount":Infinity}']
)
def test_json_rejects_duplicate_keys_and_nonfinite(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(payload)
    with pytest.raises(ContractError):
        read_json(path)


def test_unknown_schema_fields_are_rejected() -> None:
    case = case_data()
    case["assume_missing_zero"] = True
    with pytest.raises(ContractError, match="Additional properties"):
        validate(case)


def test_payment_difference_is_not_an_unsupported_omission_diagnosis(
    tmp_path: Path,
) -> None:
    case = case_data()
    case["modules"][0]["principal_paid"] = "0.00"
    case["modules"][1]["principal_paid"] = None
    case["modules"][0]["liquidation_vat"] = "0.00"
    result = calculate(case, prepare(case, tmp_path))
    assert result["modules"][0]["rows"]["vp14_debit"] == "110.00"
    assert result["modules"][0]["payment_status"] == "DIFFERENCE_TO_REVIEW"
    assert result["modules"][1]["payment_status"] == "NOT_VERIFIED"
    assert [f["code"] for f in result["findings"]] == [
        "PAYMENT_DIFFERENCE",
        "REGISTER_LIQUIDATION_DIFFERENCE",
    ]


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("vp11", "111.00", "exceeds"),
        ("vp10", "-1.00", "nonnegative"),
        ("vp13", "103.29", "Acconto"),
        ("credit_withheld", "1.00", "exceeds"),
        ("principal_paid", "-1.00", "nonnegative"),
        ("vp13_method", 1, "without amount"),
    ],
)
def test_adjustment_constraints(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    case = case_data()
    case["modules"][0][field] = value
    with pytest.raises(ContractError, match=message):
        calculate(case, prepare(case, tmp_path))


def test_persisted_result_is_hash_bound_and_never_overwritten(tmp_path: Path) -> None:
    case = case_data()
    result = calculate(case, PLUGIN / "examples")
    folder = save_result(case, result, tmp_path)
    saved = read_json(folder / "result.json")
    assert saved["result_hash"] == digest(
        {k: v for k, v in saved.items() if k != "result_hash"}
    )
    assert "110.00" in (folder / "vp.csv").read_text()
    assert "DATI SINTETICI" in (folder / "workpaper.md").read_text()
    assert "1.000,00" in (folder / "workpaper.md").read_text()
    assert (folder / "review-request.md").is_file()
    with pytest.raises(FileExistsError):
        save_result(case, result, tmp_path)


def test_cli_persists_invalid_input_and_nonzero_exit(tmp_path: Path) -> None:
    case = case_data()
    prepare(case, tmp_path)
    case["sources"][0]["sha256"] = "0" * 64
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case))
    status = main(
        [
            "calculate",
            "--case",
            str(path),
            "--source-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert status == 2
    assert next((tmp_path / "out").glob("lipe-*/result.json")).is_file()


def test_real_case_cannot_bypass_archive_with_output_flags(tmp_path: Path) -> None:
    case = case_data()
    case["data_origin"] = "REAL"
    path = tmp_path / "real.json"
    path.write_text(json.dumps(case))
    with pytest.raises(ContractError, match="Studio Archive"):
        main(
            [
                "calculate",
                "--case",
                str(path),
                "--source-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "out"),
            ]
        )


def test_extract_preserves_source_hash_and_text(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.txt"
    source.write_text("Synthetic VAT register 100,00 22,00")
    folder = extract(source, tmp_path / "out")
    receipt = read_json(folder / "extraction.json")
    assert receipt["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (folder / "page-0001.txt").read_text() == source.read_text()


def test_blank_pdf_is_not_claimed_extracted(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(source)
    folder = extract(source, tmp_path / "out")
    assert (
        read_json(folder / "extraction.json")["pages"][0]["status"]
        == "NEEDS_OCR_OR_READABLE_SOURCE"
    )


@pytest.mark.parametrize(
    "regime,quarter",
    [
        ("MONTHLY", 2),
        ("QUARTERLY_OPTION", 2),
        ("QUARTERLY_OPTION", 4),
        ("QUARTERLY_SPECIAL", 4),
    ],
)
def test_synthetic_xml_passes_official_schema(
    tmp_path: Path, regime: str, quarter: int
) -> None:
    case = case_data() if regime == "MONTHLY" else quarterly(quarter, regime)
    payload = build_test_xml(case, prepare(case, tmp_path))
    assert b"IVP18" in payload
    assert b"<iv:NumeroModulo>1</iv:NumeroModulo>" in payload


def test_real_xml_export_is_closed_until_acceptance() -> None:
    case = case_data()
    case["data_origin"] = "REAL"
    with pytest.raises(ContractError, match="Real XML export unavailable"):
        build_test_xml(case, PLUGIN / "examples")


def test_xml_schema_resolves_from_installation_with_escaped_path(
    tmp_path: Path, monkeypatch
) -> None:
    installation = tmp_path / "LIPE installation # percent% à"
    shutil.copytree(PLUGIN / "references/xsd", installation / "references/xsd")
    monkeypatch.setattr("lipe_xml.ROOT", installation)

    payload = build_test_xml(case_data(), PLUGIN / "examples")

    assert b"IVP18" in payload


def test_xml_does_not_accept_an_old_or_modified_result(tmp_path: Path) -> None:
    case = case_data()
    prepare(case, tmp_path)
    case["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(ContractError, match="Source changed"):
        build_test_xml(case, tmp_path)


def dependency_checker():
    spec = importlib.util.spec_from_file_location(
        "lipe_dependency_check", PLUGIN / "scripts/check_dependencies.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dependency_checker_accepts_declared_available_runtime() -> None:
    assert dependency_checker().main([]) == 0


def test_dependency_checker_reports_missing_requirements() -> None:
    assert dependency_checker().main(["--requirements", "missing.txt"]) == 1


def test_dependency_checker_rejects_wrong_python(monkeypatch) -> None:
    checker = dependency_checker()
    monkeypatch.setattr(checker.sys, "version_info", (3, 11))
    assert checker.main([]) == 1


def test_dependency_checker_reports_missing_package(monkeypatch) -> None:
    checker = dependency_checker()
    monkeypatch.setattr(checker.importlib.util, "find_spec", lambda name: None)
    assert checker.main([]) == 1


def test_integration_mirror_is_not_counted_twice(tmp_path: Path) -> None:
    case = case_data()
    case["mappings"][1]["treatment"] = "PURCHASE_REVERSE_CHARGE"
    mapping = copy.deepcopy(case["mappings"][1])
    mapping.update(side="INTEGRATION", treatment="INTEGRATION_MIRROR")
    case["mappings"].append(mapping)
    mirror = copy.deepcopy(case["registers"][1])
    mirror.update(register_id="mirror", side="INTEGRATION")
    mirror["rows"][0].update(
        row_id="mirror-row", deductible_tax="0.00", mirror_of=["PURCHASES-4-1"]
    )
    case["registers"].append(mirror)
    result = calculate(case, prepare(case, tmp_path))
    assert result["status"] == "DRAFT_FOR_REVIEW"
    assert result["modules"][0]["rows"]["vp2"] == "1000.00"
    assert result["modules"][0]["rows"]["vp3"] == "500.00"
    assert result["modules"][0]["rows"]["vp4"] == "330.00"


def test_integration_without_matching_purchase_blocks(tmp_path: Path) -> None:
    case = case_data()
    mapping = copy.deepcopy(case["mappings"][1])
    mapping.update(side="INTEGRATION", treatment="INTEGRATION_MIRROR")
    case["mappings"].append(mapping)
    mirror = copy.deepcopy(case["registers"][1])
    mirror.update(register_id="mirror", side="INTEGRATION")
    mirror["rows"][0].update(
        row_id="mirror-row", deductible_tax="0.00", mirror_of=["not-present"]
    )
    case["registers"].append(mirror)
    result = calculate(case, prepare(case, tmp_path))
    assert "INTEGRATION_UNLINKED:mirror-row" in result["blockers"]


def test_first_quarter_cannot_silently_consume_prior_year_credit(
    tmp_path: Path,
) -> None:
    case = quarterly(1)
    case["opening"]["credit"] = "100.00"
    with pytest.raises(ContractError, match="Prior-year credit belongs in VP9"):
        calculate(case, prepare(case, tmp_path))


def test_quarterly_small_debt_cannot_charge_interest_twice(tmp_path: Path) -> None:
    case = quarterly()
    case["opening"]["small_debit"] = "50.50"
    with pytest.raises(ContractError, match="principal/interest"):
        calculate(case, prepare(case, tmp_path))


def test_synthetic_cli_runs_and_writes_validated_xml(tmp_path: Path) -> None:
    status = main(
        [
            "xml-test",
            "--case",
            str(PLUGIN / "examples/synthetic-case.json"),
            "--source-root",
            str(PLUGIN / "examples"),
            "--output",
            str(tmp_path),
        ]
    )
    assert status == 0
    assert len(list(tmp_path.glob("SYNTHETIC_NOT_FOR_FILING-*.xml"))) == 1


def test_unreviewed_case_cannot_generate_test_xml(tmp_path: Path) -> None:
    case = case_data()
    case["opening"] = None
    with pytest.raises(ContractError, match="Blocked case"):
        build_test_xml(case, prepare(case, tmp_path))


def test_encrypted_pdf_preserves_blocker_without_reading(tmp_path: Path) -> None:
    source = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.encrypt("synthetic-password")
    writer.write(source)
    folder = extract(source, tmp_path / "out")
    assert read_json(folder / "extraction.json")["status"] == "BLOCKED_ENCRYPTED"


def test_unsupported_source_preserves_original_for_readable_derivative(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.bin"
    source.write_bytes(b"synthetic")
    folder = extract(source, tmp_path / "out")
    assert (
        read_json(folder / "extraction.json")["status"]
        == "NEEDS_REVIEWED_READABLE_DERIVATIVE"
    )


def archive_case(
    tmp_path: Path, *, wrong_identity: bool = False
) -> tuple[Path, Path, Path]:
    """Create real archive receipts around fictional test evidence."""
    spec = importlib.util.spec_from_file_location(
        "lipe_test_archive", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    assert spec is not None and spec.loader is not None
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    customer = tmp_path / "Customer"
    customer.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(customer, client_id)
    engagement = ledger.create_engagement(
        customer, client_id, "Synthetic LIPE acceptance"
    )
    case = case_data()
    prepare(case, tmp_path)
    source = ledger.import_document(
        customer,
        client_id,
        engagement["engagement_id"],
        tmp_path / "evidence.txt",
        "source",
    )
    receipt = source["receipt"]
    case["sources"][0][
        "path"
    ] = f"imports/{receipt['input_id']}/{Path(receipt['relative_path']).name}"
    case.update(
        data_origin="REAL",
        client_id="different-client" if wrong_identity else client_id,
        engagement_id=engagement["engagement_id"],
    )
    case_path = tmp_path / "reviewed-case.json"
    case_path.write_text(json.dumps(case))
    imported_case = ledger.import_document(
        customer, client_id, engagement["engagement_id"], case_path, "source"
    )
    prepared = ledger.prepare_run(
        customer,
        client_id,
        engagement["engagement_id"],
        "lipe",
        "0.1.0",
        input_ids=[receipt["input_id"], imported_case["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        customer, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    case_binding = next(
        item
        for item in running["context"]["input_bindings"]
        if item["binding_id"] == imported_case["receipt"]["input_id"]
    )
    return (
        Path(running["context_path"]),
        Path(case_binding["path"]),
        Path(running["output_dir"]),
    )


def test_archive_bound_calculation_writes_only_the_selected_run(tmp_path: Path) -> None:
    context, case_path, output = archive_case(tmp_path)
    status = main(
        ["calculate", "--case", str(case_path), "--client-engagement", str(context)]
    )
    assert status == 0
    result = read_json(next(output.glob("lipe-*/result.json")))
    assert result["status"] == "DRAFT_FOR_REVIEW"
    assert result["client_id"] == "client_111111111111111111111111"


def test_archive_identity_mismatch_is_rejected_before_calculation(
    tmp_path: Path,
) -> None:
    context, case_path, output = archive_case(tmp_path, wrong_identity=True)
    with pytest.raises(ContractError, match="archive identity differ"):
        main(
            ["calculate", "--case", str(case_path), "--client-engagement", str(context)]
        )
    assert list(output.glob("lipe-*")) == []
