"""Explicit peer decisions, reconciliations and evidence-dependent multiple review."""

from __future__ import annotations

import hashlib
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from tests.plugins.test_business_valuation import (
    FIXTURE,
    build_valuation,
    case_data,
    claimed_case,
    compile_html,
    planning_case,
    prepare_archive_run,
    read_json,
    restore_imports,
    review,
    run_valuation,
    write_package,
)


def comparable_case(base: dict | None = None) -> dict:
    """Keep both selected peers and the rejected candidate in the source-bound list."""
    case = case_data() if base is None else base
    case["sources"].append(
        {
            **case["sources"][0],
            "id": "peers",
            "path": "comparables.txt",
            "sha256": hashlib.sha256(
                (FIXTURE / "comparables.txt").read_bytes()
            ).hexdigest(),
            "description": "Fictional initial peer universe and accounting reconciliations",
        }
    )
    for name, value, unit in [
        ("target-reported", "90", "EUR"),
        ("target-lease", "10", "EUR"),
        ("target-adjusted", "100", "EUR"),
        ("alpha-reported", "700", "EUR"),
        ("alpha-lease-debt", "50", "EUR"),
        ("alpha-ev", "750", "EUR"),
        ("alpha-reported-metric", "80", "EUR"),
        ("alpha-lease-metric", "20", "EUR"),
        ("alpha-metric", "100", "EUR"),
        ("beta-ev", "1200", "EUR"),
        ("beta-metric", "120", "EUR"),
        ("selected-peer-multiple", "8", "multiple"),
    ]:
        case["inputs"].append(
            {
                **case["inputs"][0],
                "id": name,
                "value": value,
                "unit": unit,
                "source_ids": ["peers"],
                "description": "Fictional " + name,
                "locator": "comparables.txt: stated independent amount",
            }
        )
    evidence = {
        "source_ids": ["peers"],
        "locator": "comparables.txt: hypothetical decisions and conventions",
        "status": "confirmed",
    }
    period = {
        "period_start": "2025-10-01",
        "period_end": "2026-09-30",
        "period_kind": "LTM",
        "published_on": "2026-11-30",
        "metric_basis": "adjusted",
        "lease_basis": "capitalized",
        "accounting_basis": "Base sintetica con leasing capitalizzato; non è una verifica IFRS 16.",
    }

    def amount(reported, adjustments, supplied):
        return {
            "reported_input": reported,
            "adjustment_inputs": adjustments,
            "comparable_input": supplied,
            "explanation": "Importi sintetici separati; rettifiche leasing con segno, da verificare professionalmente.",
        }

    peers = []
    for name, numerator, metric in [
        (
            "alpha",
            amount("alpha-reported", ["alpha-lease-debt"], "alpha-ev"),
            amount("alpha-reported-metric", ["alpha-lease-metric"], "alpha-metric"),
        ),
        (
            "beta",
            amount("beta-ev", [], "beta-ev"),
            amount("beta-metric", [], "beta-metric"),
        ),
    ]:
        peers.append(
            {
                "id": name,
                "entity_id": name + "-company",
                "name": name.title() + " sintetica",
                "decision": "include",
                "reason": "Inclusione ipotetica esplicita, non una raccomandazione.",
                **evidence,
                "data": {
                    **period,
                    "kind": "EV_EBITDA",
                    "price_date": "2026-12-30",
                    "numerator": numerator,
                    "metric": metric,
                    "comparability": "Settore, mercati, crescita, margini, scala, rischio e leva sono assunti confrontabili solo per questa prova sintetica.",
                },
            }
        )
    peers.append(
        {
            "id": "gamma",
            "entity_id": "gamma-company",
            "name": "Gamma sintetica",
            "decision": "exclude",
            "reason": "Manca una metrica sostenibile positiva e il perimetro operativo non è comparabile.",
            **evidence,
        }
    )
    case["methods"].append(
        {
            "id": "peer-multiple",
            "kind": "MULTIPLE",
            "selected": True,
            "rationale": "Confronto sintetico con multiplo autonomamente scelto.",
            "inputs": {
                "kind": "EV_EBITDA",
                "metric": "target-adjusted",
                "selected_multiple": "selected-peer-multiple",
            },
            "limitations": ["Nessun peer reale o accettazione professionale."],
            "comparables": {
                "initial_universe": "Tre società inventate, comprese quelle escluse.",
                "selection_reason": "8x è una scelta sintetica esplicita, non la media o mediana di 8,75x.",
                "date_alignment": "Periodi LTM identici; prezzi del giorno precedente la data valutativa, solo per prova.",
                "accounting_alignment": "Raccordi da dati riportati a valori comparabili forniti; nessun fatto contabile verificato.",
                "lease_alignment": "Numeratore Alpha +50, EBITDA Alpha +20, EBITDA target +10; per Beta nessuna rettifica. Raccordo equity target non fornito.",
                "margin_analysis": "Marginalità ipoteticamente confrontabile; nessuna osservazione di mercato.",
                **evidence,
                "target": {
                    **period,
                    **evidence,
                    "metric": amount(
                        "target-reported", ["target-lease"], "target-adjusted"
                    ),
                },
                "peers": peers,
            },
        }
    )
    return case


def set_input(case, name, value):
    next(row for row in case["inputs"] if row["id"] == name)["value"] = value


def test_peer_ratios_reconcile_without_selecting_the_applied_multiple():
    result = build_valuation(comparable_case(), FIXTURE)
    values = {row["id"]: Decimal(row["value"]) for row in result["calculations"]}
    assert values["peer-multiple/comparables/alpha/multiple"] == Decimal("7.5")
    assert values["peer-multiple/comparables/beta/multiple"] == Decimal("10")
    assert values["peer-multiple/value"] == Decimal("800")
    assert result["methods"][-1]["equity_id"] is None
    assert result["methods"][-1]["comparables"]["peers"][2]["decision"] == "exclude"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("alpha-ev", "751"),
        ("alpha-lease-debt", None),
        ("target-adjusted", "99"),
        ("beta-metric", "0"),
        ("beta-metric", "-1"),
        ("beta-ev", "-10"),
    ],
)
def test_missing_inconsistent_or_negative_peer_amount_blocks_only_that_method(
    name, value
):
    case = comparable_case()
    set_input(case, name, value)
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"
    assert len(result["methods"][-1]["comparables"]["peers"]) == 3
    assert result["methods"][0]["status"] == "ready_for_professional_review"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("period_kind", "forward"),
        ("metric_basis", "reported"),
        ("lease_basis", "expensed"),
        ("kind", "P_E"),
        ("price_date", "2027-01-01"),
        ("published_on", "2027-01-01"),
        ("period_end", "2026-12-01"),
        ("period_start", "2026-10-01"),
    ],
)
def test_unaligned_peer_basis_or_lookahead_is_not_silently_used(field, value):
    case = comparable_case()
    case["methods"][-1]["comparables"]["peers"][0]["data"][field] = value
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize("kind", ["EV_EBITDA", "EV_EBIT", "EV_REVENUE", "P_E"])
def test_explicit_consistent_kind_and_forward_basis_can_be_calculated(kind):
    case = comparable_case()
    method = case["methods"][-1]
    method["inputs"]["kind"] = kind
    basis = method["comparables"]
    basis["target"].update(
        period_kind="forward", period_start="2027-01-01", period_end="2027-12-31"
    )
    for peer in basis["peers"][:2]:
        peer["data"].update(
            kind=kind,
            period_kind="forward",
            period_start="2027-01-01",
            period_end="2027-12-31",
        )
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "ready_for_professional_review"
    assert result["methods"][-1]["value_type"] == (
        "equity" if kind == "P_E" else "operating_enterprise"
    )


@pytest.mark.parametrize("field", ["id", "entity_id"])
def test_duplicate_peer_identity_is_rejected(field):
    case = comparable_case()
    peers = case["methods"][-1]["comparables"]["peers"]
    peers[1][field] = peers[0][field]
    assert build_valuation(case, FIXTURE)["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize("selected", [True, False])
def test_empty_selected_sample_retains_exclusions_and_does_not_manufacture_a_value(
    selected,
):
    case = comparable_case()
    method = case["methods"][-1]
    method["selected"] = selected
    for peer in method["comparables"]["peers"]:
        peer["decision"] = "exclude"
        peer.pop("data", None)
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == ("blocked" if selected else "excluded")
    assert len(result["methods"][-1]["comparables"]["peers"]) == 3
    assert "value_id" not in result["methods"][-1]
    assert "Gamma sintetica" in compile_html(result)


@pytest.mark.parametrize("scope", ["group", "target", "included", "excluded", "source"])
def test_unconfirmed_peer_decisions_or_evidence_keep_method_partial(scope):
    case = comparable_case()
    basis = case["methods"][-1]["comparables"]
    records = {
        "group": basis,
        "target": basis["target"],
        "included": basis["peers"][0],
        "excluded": basis["peers"][2],
        "source": case["sources"][-1],
    }
    records[scope]["status"] = "unverified" if scope == "source" else "proposed"
    assert build_valuation(case, FIXTURE)["methods"][-1]["status"] == "partial"


@pytest.mark.parametrize("scope", ["exclusion", "selection", "amount", "accounting"])
def test_changed_peer_dependency_expires_its_review_but_preserves_independent_method(
    scope,
):
    case = comparable_case()
    before = build_valuation(case, FIXTURE)
    case["methods"][-1]["review"] = review(before["methods"][-1]["dependency_sha256"])
    case["methods"][0]["review"] = review(before["methods"][0]["dependency_sha256"])
    basis = case["methods"][-1]["comparables"]
    if scope == "exclusion":
        basis["peers"][2]["reason"] += " Revised."
    elif scope == "selection":
        basis["selection_reason"] += " Revised."
    elif scope == "amount":
        set_input(case, "beta-ev", "1000")
    else:
        basis["peers"][0]["data"]["accounting_basis"] += " Revised."
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["stale_review"] is True
    assert result["methods"][0]["status"] == "accepted_workpaper"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adjustment_inputs", ["alpha-lease-debt", "alpha-lease-debt"]),
        ("adjustment_inputs", ["alpha-ev"]),
        ("reported_input", "alpha-ev"),
        ("comparable_input", "unknown"),
    ],
)
def test_reconciliation_rejects_reused_or_missing_amounts(field, value):
    case = comparable_case()
    case["methods"][-1]["comparables"]["peers"][0]["data"]["numerator"][field] = value
    assert build_valuation(case, FIXTURE)["methods"][-1]["status"] == "blocked"


def test_workpaper_must_reconcile_the_metric_actually_valued():
    case = comparable_case()
    case["methods"][-1]["inputs"]["metric"] = "flow"
    assert build_valuation(case, FIXTURE)["methods"][-1]["status"] == "blocked"


def test_unknown_source_cannot_support_a_peer_exclusion():
    case = comparable_case()
    case["methods"][-1]["comparables"]["peers"][2]["source_ids"] = ["missing"]
    assert build_valuation(case, FIXTURE)["methods"][-1]["status"] == "blocked"


def test_declared_peer_workpaper_is_not_accepted_on_a_different_method():
    case = comparable_case()
    case["methods"][0]["comparables"] = case["methods"][-1]["comparables"]
    assert build_valuation(case, FIXTURE)["methods"][0]["status"] == "blocked"


def test_peer_export_keeps_exclusions_and_literal_text_with_linked_formulas(tmp_path):
    from openpyxl import load_workbook

    case = comparable_case()
    basis = case["methods"][-1]["comparables"]
    basis["initial_universe"] = '=HYPERLINK("https://example.invalid")'
    basis["peers"][2]["reason"] = '<script>alert("source")</script>'
    result = build_valuation(case, FIXTURE)
    output = tmp_path / "report"
    write_package(result, FIXTURE, output)
    workbook = load_workbook(output / "valuation_workbook.xlsx")
    assert workbook["Base multipli"]["D2"].data_type == "s"
    assert workbook["Comparabili"]["E2"].data_type == "f"
    assert workbook["Comparabili"]["C4"].value == "Escluso"
    assert workbook["Raccordi multipli"]["D2"].data_type == "f"
    assert "<script>alert" not in compile_html(result)
    assert "&lt;script&gt;alert" in compile_html(result)
    assert read_json(output / "valuation.json") == result


def test_comparable_workflow_runs_with_exact_archive_receipts(
    tmp_path, record_property
):
    case_path, context = prepare_archive_run(
        tmp_path,
        supplied_case=comparable_case(),
        source_files=[FIXTURE / "evidence.txt", FIXTURE / "comparables.txt"],
    )
    output = run_valuation.run_case(case_path, context)
    report = read_json(Path(output["output_dir"]) / "valuation.json")
    assert report["methods"][-1]["status"] == "ready_for_professional_review"
    assert len(report["methods"][-1]["comparables"]["peers"]) == 3
    record_property("comparable_output", output["output_dir"])


def test_plan_fcff_cannot_be_used_as_a_peer_adjustment(tmp_path):
    case = comparable_case(planning_case(tmp_path))
    shutil.copyfile(FIXTURE / "comparables.txt", tmp_path / "comparables.txt")
    numerator = case["methods"][-1]["comparables"]["peers"][0]["data"]["numerator"]
    numerator["adjustment_inputs"] = ["flow"]
    set_input(case, "alpha-reported", "2000")
    set_input(case, "alpha-ev", "800")
    result = build_valuation(case, tmp_path, replay_parent=tmp_path / "replay")
    assert result["methods"][-1]["status"] == "blocked"
    assert "cannot be relabelled" in result["methods"][-1]["reason"]


def test_changed_exclusion_invalidates_a_claim_even_if_the_indication_is_unchanged():
    case = comparable_case(claimed_case())
    claim = case["claims"][0]
    claim.update(
        calculation_ids=["peer-multiple/value"],
        values=[
            {"calculation_id": "peer-multiple/value", "value": "800", "unit": "EUR"}
        ],
    )
    first = build_valuation(case, FIXTURE)
    case["methods"][-1]["review"] = review(first["methods"][-1]["dependency_sha256"])
    case["mandate_details"]["review"] = review(
        first["mandate_assessment"]["dependency_sha256"]
    )
    second = build_valuation(case, FIXTURE)
    claim["review"] = review(second["claims"][0]["dependency_sha256"])
    case["methods"][-1]["comparables"]["peers"][2]["reason"] += " Nuova motivazione."
    result = build_valuation(case, FIXTURE)
    assert result["claims"][0]["stale_review"] is True
    assert result["claims"][0]["status"] != "accepted_workpaper"


@pytest.mark.parametrize("selected", [True, False])
def test_empty_evidence_binding_never_becomes_an_accepted_peer_workpaper(selected):
    case = comparable_case()
    method = case["methods"][-1]
    method["selected"] = selected
    method["comparables"]["source_ids"] = []
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == ("blocked" if selected else "excluded")
    assert "comparables" not in result["methods"][-1]
