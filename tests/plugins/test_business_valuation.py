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
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
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


def test_unsupported_method_remains_visible_in_partial_exports(tmp_path: Path) -> None:
    case = case_data()
    case["methods"][0]["kind"] = "SPECIALIST_METHOD"
    result = build_valuation(case, FIXTURE)
    output = tmp_path / "partial"
    write_package(result, FIXTURE, output)
    assert result["methods"][0]["status"] == "blocked"
    assert (
        "Metodo non supportato: SPECIALIST_METHOD"
        in (output / "valuation_report.md").read_text()
    )


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


@pytest.mark.parametrize(
    "profile_id",
    [
        "sale",
        "contribution",
        "transformation",
        "merger",
        "demerger",
        "capital_increase",
        "withdrawal",
        "exclusion",
        "inheritance",
        "family",
        "tax",
        "accounting",
        "ppa",
        "litigation",
        "distress",
        "liquidation",
        "collateral",
        "strategy",
        "fairness",
        "review",
        "custom",
    ],
)
def test_explicit_purpose_intake_does_not_enable_professional_use(
    profile_id: str,
) -> None:
    case = case_data()
    case["purpose_profile"] = {
        "id": profile_id,
        "selection_reason": "Explicit choice for synthetic intake only",
        "source_ids": [case["sources"][0]["id"]],
        "locator": "Synthetic mandate paragraph 1",
    }

    result = build_valuation(case, FIXTURE)

    assert result["purpose_coverage"]["profile"]["id"] == profile_id
    assert result["purpose_coverage"]["coverage"]["professional_use_enabled"] is False
    assert result["purpose_coverage"]["coverage"]["professional_review"] == "pending"
    assert result["piv_conformity"] == "not_assessed"


def test_purpose_change_invalidates_previous_method_acceptance() -> None:
    case = case_data()
    prior = build_valuation(case, FIXTURE)
    case["methods"][0]["review"] = review(prior["methods"][0]["dependency_sha256"])
    case["purpose_profile"] = {
        "id": "withdrawal",
        "selection_reason": "The clarified mandate concerns withdrawal rights",
        "source_ids": [case["sources"][0]["id"]],
        "locator": "Synthetic mandate paragraph 1",
    }

    result = build_valuation(case, FIXTURE)

    assert result["methods"][0]["stale_review"] is True
    assert result["methods"][0]["status"] == "ready_for_professional_review"


def test_unknown_purpose_profile_is_not_guessed_from_its_name() -> None:
    case = case_data()
    case["purpose_profile"] = {
        "id": "sale_and_merger",
        "selection_reason": "Ambiguous synthetic choice",
        "source_ids": [case["sources"][0]["id"]],
        "locator": "Synthetic mandate paragraph 1",
    }

    with pytest.raises(ValuationError, match="Unknown purpose profile"):
        build_valuation(case, FIXTURE)


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


def test_sensitivity_cannot_revive_an_excluded_method() -> None:
    case = case_data()
    case["methods"][0]["selected"] = False
    case["sensitivity"] = [
        dict(
            id="scenario",
            method_id="fcff",
            discount_rate="rate",
            terminal_rate="rate",
            terminal_growth="growth",
        )
    ]
    with pytest.raises(ValuationError, match="selected DCF"):
        build_valuation(case, FIXTURE)


def test_plan_lineage_without_a_replayed_plan_is_rejected() -> None:
    case = case_data()
    case["inputs"][0]["plan_calculation_ids"] = ["invented"]
    with pytest.raises(ValuationError, match="plan binding"):
        build_valuation(case, FIXTURE)


@pytest.mark.parametrize("change_conclusion", [False, True])
def test_conclusion_acceptance_is_bound_to_its_exact_text(
    change_conclusion: bool,
) -> None:
    case = case_data()
    initial = build_valuation(case, FIXTURE)
    case["methods"][0]["review"] = review(initial["methods"][0]["dependency_sha256"])
    case["conclusion"] = {
        "text": "Synthetic conclusion",
        "method_ids": ["fcff"],
        "review": None,
    }
    draft = build_valuation(case, FIXTURE)
    case["conclusion"]["review"] = review(draft["conclusion"]["dependency_sha256"])
    if change_conclusion:
        case["conclusion"]["text"] = "Changed conclusion"
    result = build_valuation(case, FIXTURE)
    assert result["conclusion"]["status"] == (
        "draft" if change_conclusion else "accepted_workpaper"
    )
    assert result["status"] == (
        "ready_for_professional_review" if change_conclusion else "accepted_workpaper"
    )


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
    tmp_path: Path,
    workflow: str = "business-valuation",
    *,
    supplied_case: dict | None = None,
    source_files: list[Path] | None = None,
) -> tuple[Path, Path]:
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    ledger = _load_customer_ledger()
    client = tmp_path / "Client"
    client.mkdir()
    identity = "client_111111111111111111111111"
    ledger.create_client_manifest(client, identity)
    engagement = ledger.create_engagement(client, identity, "Synthetic valuation")
    case = deepcopy(supplied_case) if supplied_case is not None else case_data()
    input_ids = []
    for index, source_file in enumerate(source_files or [FIXTURE / "evidence.txt"]):
        receipt = ledger.import_document(
            client, identity, engagement["engagement_id"], source_file, "source"
        )["receipt"]
        input_ids.append(receipt["input_id"])
        case["sources"][index][
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
        input_ids=[*input_ids, imported["receipt"]["input_id"]],
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


@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_valuation_teaching_sources_run_the_bound_workflow(
    tmp_path: Path, phase: str, record_property
) -> None:
    """Interpret the supplied fictional note explicitly; never ship a preapproved case."""
    from tests.plugins._teaching_release import record_native_check

    folder = ROOT / "plugins/vera/assets/courses/business-valuation/files"
    sources = [folder / "input/caso-it.md"]
    case = case_data()
    case["entity_name"] = "Officina Arco — esercizio sintetico"
    case["purpose_profile"] = {
        "id": "strategy",
        "selection_reason": "La nota richiede un confronto interno su ipotesi didattiche, senza finalità legale.",
        "source_ids": [case["sources"][0]["id"]],
        "locator": "caso-it.md: incarico e base ipotetica per confronto interno",
    }
    case["methods"] = [case["methods"][0]]
    case["methods"][0][
        "rationale"
    ] = "La nota propone flussi FCFF annuali e un raccordo esplicito; le altre basi non sono disponibili."
    case["methods"][0]["limitations"] = [
        "Tassi didattici, sostenibilità non dimostrata, nessuna finalità legale qualificata."
    ]
    needed = {"flow", "terminal", "rate", "growth", "debt", "cash", "zero"}
    case["inputs"] = [item for item in case["inputs"] if item["id"] in needed]
    for item in case["inputs"]:
        if item["unit"] == "EUR":
            item["value"] = str(Decimal(item["value"]) * 1000)
        item["description"] = f"Ipotesi didattica: {item['id']}"
        item["locator"] = "caso-it.md: flussi, tassi e raccordo"
    assert "100.000" in sources[0].read_text()
    case["sources"][0].update(
        path="caso-it.md",
        description="Nota didattica sintetica",
        sha256=hashlib.sha256(sources[0].read_bytes()).hexdigest(),
    )
    if phase == "practice":
        sources.append(folder / "practice/pratica-it.md")
        assert "12%" in sources[1].read_text()
        case["sources"].append(
            {
                **case["sources"][0],
                "id": "update",
                "path": "pratica-it.md",
                "sha256": hashlib.sha256(sources[1].read_bytes()).hexdigest(),
            }
        )
        rate = next(item for item in case["inputs"] if item["id"] == "rate")
        rate.update(
            value="0.12",
            source_ids=["update"],
            locator="pratica-it.md: tasso di sconto e terminale",
        )
    case_path, context = prepare_archive_run(
        tmp_path, supplied_case=case, source_files=sources
    )
    output = run_valuation.run_case(case_path, context)
    result_path = Path(output["output_dir"]) / "valuation.json"
    report = read_json(result_path)
    amounts = {row["id"]: Decimal(row["value"]) for row in report["calculations"]}
    expected = (
        Decimal("750000")
        if phase == "demo"
        else Decimal("583333.3333333333333333333333333333333333")
    )
    assert abs(amounts["fcff/equity"] - expected) < Decimal("0.000001")
    assert report["status"] == "ready_for_professional_review"
    assert report["conclusion"] is None
    assert report["purpose_coverage"]["profile"]["id"] == "strategy"
    assert report["purpose_coverage"]["coverage"]["professional_use_enabled"] is False
    record_property("teaching_output", output["output_dir"])
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="business-valuation",
        language="it",
        phase=phase,
    )


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


def planning_case(tmp_path: Path) -> dict:
    """Reuse the real v3 synthetic case and compiler with a full calendar year."""
    scripts = ROOT / "plugins/business-planning/scripts"
    sys.path.insert(0, str(scripts))
    from planning_workflow import build_plan

    planning_fixture = ROOT / "tests/fixtures/business_planning"
    upstream = read_json(planning_fixture / "case.json")
    periods = [f"2027-{month:02}" for month in range(1, 13)]
    upstream["periods"] = periods
    upstream["assumptions"][0]["effective_periods"] = periods
    for scenario in upstream["financial"]["scenarios"]:
        original = deepcopy(scenario["schedule"][-1])
        scenario["schedule"].extend(
            {**deepcopy(original), "period": period} for period in periods[3:]
        )
    plan = build_plan(upstream, source_root=planning_fixture)
    assert plan["status"] == "ready_for_professional_review"
    case = case_data()
    shutil.copy(FIXTURE / "evidence.txt", tmp_path / "evidence.txt")
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    case["sources"].append(
        dict(
            id="plan",
            path="plan.json",
            sha256=hashlib.sha256((tmp_path / "plan.json").read_bytes()).hexdigest(),
            description="Replayed synthetic v3 plan",
            allowed_audiences=["internal"],
            status="reviewed",
        )
    )
    mapping = {}
    for original in upstream["sources"]:
        name = f"plan-{original['id']}.txt"
        shutil.copy(planning_fixture / original["path"], tmp_path / name)
        identifier = f"plan-{original['id']}"
        mapping[original["id"]] = identifier
        case["sources"].append(
            dict(
                id=identifier,
                path=name,
                sha256=original["sha256"],
                description="Original plan source",
                allowed_audiences=["internal"],
                status="reviewed",
            )
        )
    case["inputs"][0].update(
        value="-1200",
        source_ids=["plan"],
        plan_calculation_ids=[
            f"base/{period}/{metric}"
            for period in periods
            for metric in ("ebit", "working_capital")
        ],
    )
    case["plan_binding"] = dict(
        source_id="plan",
        source_map=mapping,
        scenario_id="base",
        cash_operating_taxes={period: "zero" for period in periods},
        opening_operating_nwc="zero",
        annual_input_ids=["flow"],
        operating_classification="All supplied current positions are operating; synthetic zero opening NWC",
        tax_refund_basis="",
    )
    return case


def test_existing_plan_bridge_replays_and_reconciles_annual_fcff(
    tmp_path: Path,
) -> None:
    case = planning_case(tmp_path)
    result = build_valuation(case, tmp_path, replay_parent=tmp_path / "replay")
    assert result["plan_bridge"]["annual"][0]["fcff"] == "-1200"
    assert result["plan_bridge"]["annual"][0]["ending_nwc"] == "0"
    assert len(result["plan_bridge"]["monthly"]) == 12
    assert (
        result["plan_bridge"]["monthly"][0]["plan_calculation_ids"][0]
        == "base/2027-01/ebit"
    )


def test_plan_bridge_requires_every_month_cash_tax(tmp_path: Path) -> None:
    case = planning_case(tmp_path)
    del case["plan_binding"]["cash_operating_taxes"]["2027-01"]
    with pytest.raises(ValuationError, match="every month"):
        build_valuation(case, tmp_path, replay_parent=tmp_path / "replay")


def test_plan_bridge_rejects_arbitrary_annual_flow(tmp_path: Path) -> None:
    case = planning_case(tmp_path)
    case["inputs"][0]["value"] = "-1190"
    with pytest.raises(ValuationError, match="differs from replayed"):
        build_valuation(case, tmp_path, replay_parent=tmp_path / "replay")


def test_plan_bridge_pending_cash_tax_prevents_acceptance(tmp_path: Path) -> None:
    case = planning_case(tmp_path)
    next(item for item in case["inputs"] if item["id"] == "zero")["status"] = "proposed"
    result = build_valuation(case, tmp_path, replay_parent=tmp_path / "replay")
    assert result["methods"][0]["status"] == "partial"
