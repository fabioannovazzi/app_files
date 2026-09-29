"""Numerical, evidence and portable-run acceptance for PMI valuation workpapers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/business-valuation/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))

import run_valuation
import valuation_case
import valuation_engine
import valuation_report
from valuation_case import build_valuation, digest, read_json
from valuation_engine import ValuationError, decimal, evaluate
from valuation_report import compile_html, write_package, write_workbook

FIXTURE = ROOT / "tests/fixtures/business_valuation"


@pytest.fixture(autouse=True)
def restore_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep isolated component imports available after repository test cleanup."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for module in (run_valuation, valuation_case, valuation_engine, valuation_report):
        monkeypatch.setitem(sys.modules, module.__name__, module)


def case_data() -> dict:
    return read_json(FIXTURE / "case.json")


def review(dependency: str) -> dict:
    return {
        "dependency_sha256": dependency,
        "decision": "accepted",
        "reviewer": "Synthetic reviewer",
        "reviewed_at": "2026-09-29T17:00:00+02:00",
    }


@pytest.mark.parametrize(
    ("calculation_id", "expected"),
    [
        ("fcff/value", "1000"),
        ("fcff/equity", "750"),
        ("fcfe/value", "1000"),
        ("income-method/value", "1000"),
        ("nav/value", "650"),
        ("mixed/value", "681.8181818181818181818181818181818181818"),
        ("multiple-method/equity", "250"),
        ("apv/equity", "930"),
    ],
)
def test_supported_methods_have_independent_expected_results(
    calculation_id: str, expected: str
) -> None:
    result = build_valuation(case_data(), FIXTURE)
    values = {row["id"]: row["value"] for row in result["calculations"]}
    assert Decimal(values[calculation_id]) == Decimal(expected)
    assert result["piv_conformity"] == "not_assessed"
    assert result["status"] == "ready_for_professional_review"


@pytest.mark.parametrize(
    "invalid",
    [None, 1, 0.1, True, "NaN", "Infinity", "1e5", "1,000", "+1", "01", "9" * 81],
)
def test_noncanonical_or_missing_number_is_never_zero(invalid: object) -> None:
    with pytest.raises(ValuationError):
        decimal(invalid)


def test_missing_flow_blocks_only_dependent_methods() -> None:
    case = case_data()
    case["inputs"][0]["value"] = None
    result = build_valuation(case, FIXTURE)
    states = {row["method_id"]: row["status"] for row in result["methods"]}
    assert result["status"] == "partial"
    assert states["fcff"] == "blocked"
    assert states["nav"] == "ready_for_professional_review"


def test_equity_method_rejects_second_debt_deduction() -> None:
    case = case_data()
    case["methods"][1]["bridge"] = case["methods"][0]["bridge"]
    result = build_valuation(case, FIXTURE)
    assert result["methods"][1]["status"] == "blocked"
    assert "again" in result["methods"][1]["reason"]


def test_invalid_terminal_growth_is_blocked() -> None:
    case = case_data()
    case["inputs"][3]["value"] = "0.1"
    result = build_valuation(case, FIXTURE)
    assert result["methods"][0]["status"] == "blocked"


def test_unit_mismatch_is_not_implicitly_converted() -> None:
    case = case_data()
    case["inputs"][0]["unit"] = "ratio"
    result = build_valuation(case, FIXTURE)
    assert "unit" in result["methods"][0]["reason"]


def test_source_tampering_prevents_any_export(tmp_path: Path) -> None:
    shutil.copy(FIXTURE / "evidence.txt", tmp_path / "evidence.txt")
    (tmp_path / "evidence.txt").write_text("changed source")
    with pytest.raises(ValuationError, match="Source bytes changed"):
        build_valuation(case_data(), tmp_path)


def test_audience_change_requires_permitted_sources() -> None:
    case = case_data()
    case["audience"] = "bank"
    with pytest.raises(ValuationError, match="audience"):
        build_valuation(case, FIXTURE)


def test_source_traversal_is_rejected() -> None:
    case = case_data()
    case["sources"][0]["path"] = "../business_valuation/evidence.txt"
    with pytest.raises(ValuationError, match="contained"):
        build_valuation(case, FIXTURE)


def test_changed_input_invalidates_only_dependent_reviews() -> None:
    case = case_data()
    initial = build_valuation(case, FIXTURE)
    case["methods"][0]["review"] = review(initial["methods"][0]["dependency_sha256"])
    case["methods"][3]["review"] = review(initial["methods"][3]["dependency_sha256"])
    case["inputs"][0]["value"] = "120"
    result = build_valuation(case, FIXTURE)
    assert result["methods"][0]["stale_review"] is True
    assert result["methods"][0]["status"] == "ready_for_professional_review"
    assert result["methods"][3]["status"] == "accepted_workpaper"


def test_proposed_input_cannot_be_accepted_with_a_hash() -> None:
    case = case_data()
    case["inputs"][0]["status"] = "proposed"
    initial = build_valuation(case, FIXTURE)
    case["methods"][0]["review"] = review(initial["methods"][0]["dependency_sha256"])
    result = build_valuation(case, FIXTURE)
    assert result["methods"][0]["status"] == "partial"


def test_benchmark_publication_after_cutoff_is_rejected() -> None:
    case = case_data()
    case["inputs"][2]["benchmark"] = dict(
        source_url="https://example.org/source",
        observed_on="2026-12-30",
        published_on="2027-01-03",
        retrieved_on="2027-01-04",
        vintage="synthetic",
        definition="Annual rate",
        geography="Synthetic",
        max_age_days=10,
        selection_reason="Synthetic test",
    )
    with pytest.raises(ValuationError, match="look-ahead"):
        build_valuation(case, FIXTURE)


def test_invalid_sensitivity_is_retained_without_corrupting_base() -> None:
    case = case_data()
    case["sensitivity"] = [
        dict(
            id="bad-rate",
            method_id="fcff",
            discount_rate="rate",
            terminal_rate="rate",
            terminal_growth="rate",
        )
    ]
    result = build_valuation(case, FIXTURE)
    assert result["sensitivity"][0]["status"] == "blocked"
    assert result["methods"][0]["status"] == "ready_for_professional_review"


def test_report_replay_rejects_tampered_derived_values(tmp_path: Path) -> None:
    result = build_valuation(case_data(), FIXTURE)
    result["calculations"][-1]["value"] = "999999"
    result["report_sha256"] = digest(
        {key: value for key, value in result.items() if key != "report_sha256"}
    )
    with pytest.raises(ValuationError, match="canonical replay"):
        write_package(result, FIXTURE, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_html_escapes_authored_content() -> None:
    case = case_data()
    case["entity_name"] = "<script>alert('x')</script>"
    result = compile_html(build_valuation(case, FIXTURE))
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_workbook_formulas_replay_to_engine_values(tmp_path: Path) -> None:
    from openpyxl import load_workbook

    report = build_valuation(case_data(), FIXTURE)
    path = tmp_path / "valuation.xlsx"
    write_workbook(path, report)
    workbook = load_workbook(path, data_only=False)
    cells = {}
    for index, record in enumerate(report["calculations"], 2):
        value = workbook["Calcoli"].cell(index, 2).value
        if isinstance(value, (int, float)):
            calculated = Decimal(str(value))
        elif value.startswith("='Dati'!"):
            calculated = Decimal(str(workbook["Dati"][value.split("!")[1]].value))
        elif value == "=0":
            calculated = Decimal(0)
        elif value.startswith("=SUM("):
            calculated = evaluate("sum", [cells[key] for key in value[5:-1].split(",")])
        else:
            match = re.fullmatch(r"=(B\d+)([-*/^])(B\d+)", value)
            assert match is not None
            op = {"-": "subtract", "*": "multiply", "/": "divide", "^": "power"}[
                match[2]
            ]
            calculated = evaluate(op, [cells[match[1]], cells[match[3]]])
        cells[f"B{index}"] = calculated
        assert abs(calculated - Decimal(record["value"])) < Decimal("0.00000001")
    assert workbook["Sintesi"]["C5"].value.startswith("='Calcoli'!")


def test_workbook_untrusted_labels_are_literal(tmp_path: Path) -> None:
    from openpyxl import load_workbook

    case = case_data()
    case["entity_name"] = '=HYPERLINK("https://example.org")'
    case["inputs"][0]["description"] = "=1+1"
    path = tmp_path / "literal.xlsx"
    write_workbook(path, build_valuation(case, FIXTURE))
    workbook = load_workbook(path)
    assert workbook["Sintesi"]["B1"].data_type == "s"
    assert workbook["Dati"]["B2"].data_type == "s"


def test_export_formats_are_readable_and_preserve_status(tmp_path: Path) -> None:
    from docx import Document
    from pypdf import PdfReader

    report = build_valuation(case_data(), FIXTURE)
    output = tmp_path / "report"
    artifacts = write_package(report, FIXTURE, output)
    assert len(artifacts) == 7
    assert (
        Document(output / "valuation_report.docx").paragraphs[0].text
        == "Valutazione d’impresa"
    )
    assert (
        "Carte di lavoro"
        in PdfReader(output / "valuation_report.pdf").pages[0].extract_text()
    )
    assert (
        read_json(output / "valuation.json")["status"]
        == "ready_for_professional_review"
    )


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"value":"1","value":"2"}')
    with pytest.raises(ValuationError, match="Duplicate JSON"):
        read_json(path)


def prepare_archive_run(
    tmp_path: Path, workflow: str = "business-valuation"
) -> tuple[Path, Path]:
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    ledger = _load_customer_ledger()
    client = tmp_path / "Client"
    client.mkdir()
    identity = "client_111111111111111111111111"
    ledger.create_client_manifest(client, identity)
    engagement = ledger.create_engagement(client, identity, "Synthetic valuation")
    evidence = ledger.import_document(
        client,
        identity,
        engagement["engagement_id"],
        FIXTURE / "evidence.txt",
        "source",
    )
    receipt = evidence["receipt"]
    case = case_data()
    case["sources"][0][
        "path"
    ] = f"imports/{receipt['input_id']}/{Path(receipt['relative_path']).name}"
    original = tmp_path / "case.json"
    original.write_text(json.dumps(case))
    imported = ledger.import_document(
        client, identity, engagement["engagement_id"], original, "source"
    )
    prepared = ledger.prepare_run(
        client,
        identity,
        engagement["engagement_id"],
        workflow,
        "development",
        input_ids=[receipt["input_id"], imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    case_path = next(
        Path(row["path"])
        for row in running["context"]["input_bindings"]
        if row["binding_id"] == imported["receipt"]["input_id"]
    )
    return case_path, Path(running["context_path"])


def test_portable_archive_run_exports_and_replays_idempotently(tmp_path: Path) -> None:
    case_path, context = prepare_archive_run(tmp_path)
    first = run_valuation.run_case(case_path, context)
    second = run_valuation.run_case(case_path, context)
    assert first == second
    assert first["status"] == "ready_for_professional_review"
    assert Path(first["output_dir"]).is_relative_to(tmp_path / "Client")


def test_other_workflow_context_is_rejected(tmp_path: Path) -> None:
    case_path, context = prepare_archive_run(tmp_path, "financial-analysis")
    with pytest.raises(ValueError, match="different Vera workflow"):
        run_valuation.run_case(case_path, context)
