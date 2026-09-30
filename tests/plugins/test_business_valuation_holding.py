"""Holding parts, explicit ownership, parent exposure and evidence-bound review."""

from __future__ import annotations

import hashlib
import shutil
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from test_business_valuation import (
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


def holding_case(base: dict | None = None) -> dict:
    """Use independent fictitious amounts; no peer, right or tax rule is inferred."""
    case = case_data() if base is None else base
    case["sources"].append(
        {
            **case["sources"][0],
            "id": "holding-basis",
            "path": "holding-sotp.txt",
            "sha256": hashlib.sha256(
                (FIXTURE / "holding-sotp.txt").read_bytes()
            ).hexdigest(),
            "description": "Fictional holding parts, rights and parent-only adjustments",
        }
    )
    template = case["inputs"][0]
    amounts = [
        ("alpha-value", "1000", "EUR"),
        ("alpha-debt", "200", "EUR"),
        ("alpha-debtlike", "20", "EUR"),
        ("alpha-cash", "50", "EUR"),
        ("alpha-assets", "30", "EUR"),
        ("alpha-adjustment", "-10", "EUR"),
        ("alpha-share", "0.6", "ratio"),
        ("alpha-rights", "-15", "EUR"),
        ("beta-value", "400", "EUR"),
        ("beta-share", "0.25", "ratio"),
        ("beta-rights", "0", "EUR"),
        ("gamma-value", "120", "EUR"),
        ("parent-cash", "80", "EUR"),
        ("parent-receivable", "60", "EUR"),
        ("parent-debt", "150", "EUR"),
        ("parent-costs", "30", "EUR"),
        ("parent-tax", "20", "EUR"),
        ("eliminate-receivable", "-60", "EUR"),
    ]
    case["inputs"].extend(
        {
            **template,
            "id": key,
            "value": value,
            "unit": unit,
            "source_ids": ["holding-basis"],
            "description": f"Fictional {key}",
            "locator": "holding-sotp.txt: independent stated amount",
        }
        for key, value, unit in amounts
    )
    evidence = {
        "source_ids": ["holding-basis"],
        "locator": "holding-sotp.txt: synthetic scope and assumptions",
        "status": "confirmed",
    }
    parts = []
    for name, value_type in [
        ("alpha", "operating_enterprise"),
        ("beta", "full_equity"),
        ("gamma", "specific_interest"),
    ]:
        part = {
            "id": name,
            "value_type": value_type,
            "value": name + "-value",
            "basis": {
                "entity_id": name,
                "interest_id": name + "-interest",
                "ownership_denominator_id": (
                    None if name == "gamma" else "common-equity"
                ),
                "valuation_date": case["mandate"]["valuation_date"],
                "currency": "EUR",
                "description": f"Partecipazione sintetica {name}",
                "scope": "Valore autonomo alla data; Gamma include anche il credito holding dichiarato.",
                "ownership_basis": "Denominatore esplicito per la quota; Gamma è già il diritto detenuto.",
                "rights_basis": "Rettifica dichiarata; nessun premio o sconto inferito. Gamma include i propri diritti.",
                **evidence,
            },
        }
        if name != "gamma":
            part.update(ownership=name + "-share", rights_adjustment=name + "-rights")
        if name == "alpha":
            part["bridge"] = {
                "financial_debt": "alpha-debt",
                "debt_like": "alpha-debtlike",
                "excess_cash": "alpha-cash",
                "non_operating_assets": "alpha-assets",
                "signed_adjustments": "alpha-adjustment",
            }
        parts.append(part)
    case["methods"].append(
        {
            "id": "holding",
            "kind": "HOLDING_SOTP",
            "selected": True,
            "rationale": "Composizione sintetica distinta dagli altri confronti indipendenti.",
            "inputs": {
                "holdings": parts,
                "parent_assets": ["parent-cash", "parent-receivable"],
                "parent_liabilities": ["parent-debt"],
                "holding_costs_pv": "parent-costs",
                "tax_adjustment": "parent-tax",
                "eliminations": [
                    {
                        "id": "receivable-overlap",
                        "amount_input": "eliminate-receivable",
                        "affected_input_ids": ["gamma-value", "parent-receivable"],
                        "reason": "Elimina una sola volta il credito incluso anche nel valore del diritto Gamma.",
                        **evidence,
                    }
                ],
            },
            "holding_basis": {
                "parent_perimeter": "Solo cassa, credito e passività autonome dichiarate della holding.",
                "costs_basis": "Valore attuale sintetico autonomo di 30; non è un costo annuo.",
                "tax_basis": "Deduzione sintetica di 20, separata dalle partecipate; nessuna aliquota automatica.",
                "intragroup_basis": "Il credito di 60 è incluso due volte nei dati forniti; eliminazione esplicita -60.",
                "overlap_review": "Confronto delle unità di conto dichiarate; nessuna attestazione di completezza reale.",
                "rights_scope": "Capitale proprio della holding ipotetica; nessuna waterfall o ripartizione fra soci.",
                **evidence,
            },
            "limitations": [
                "Esempio sintetico. Diritti, valori, imposte e perimetri richiedono revisione professionale."
            ],
        }
    )
    return case


def set_amount(case: dict, name: str, value: str | None) -> None:
    next(row for row in case["inputs"] if row["id"] == name)["value"] = value


def test_holding_composes_stakes_once_before_parent_exposures():
    result = build_valuation(holding_case(), FIXTURE)
    values = {row["id"]: Decimal(row["value"]) for row in result["calculations"]}
    assert values["holding/holding/alpha/equity"] == Decimal("850")
    assert values["holding/holding/alpha/stake"] == Decimal("495")
    assert values["holding/holding/beta/stake"] == Decimal("100")
    assert values["holding/holdings_value"] == Decimal("715")
    assert values["holding/value"] == Decimal("595")
    assert result["methods"][-1]["equity_id"] == "holding/value"
    assert result["methods"][-1]["holding_schedule"]["parts"][2]["ownership_id"] is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("alpha-value", None),
        ("parent-tax", None),
        ("eliminate-receivable", None),
        ("alpha-share", "1.01"),
        ("alpha-share", "-0.1"),
        ("alpha-debt", "-1"),
        ("alpha-cash", "-1"),
        ("parent-debt", "-1"),
        ("parent-costs", "-1"),
    ],
)
def test_missing_or_invalid_holding_amount_blocks_only_its_method(name, value):
    case = holding_case()
    set_amount(case, name, value)
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"
    assert result["methods"][0]["status"] == "ready_for_professional_review"


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("alpha-value", "100", "55"),
        ("parent-tax", "-20", "635"),
        ("alpha-rights", "15", "625"),
        ("parent-debt", "1000", "-255"),
        ("alpha-share", "0", "85"),
        ("alpha-share", "1", "935"),
    ],
)
def test_signed_values_and_explicit_ownership_have_no_hidden_floor(
    name, value, expected
):
    case = holding_case()
    set_amount(case, name, value)
    result = build_valuation(case, FIXTURE)
    value_row = next(
        row for row in result["calculations"] if row["id"] == "holding/value"
    )
    assert Decimal(value_row["value"]) == Decimal(expected)


@pytest.mark.parametrize("index", [1, 2])
def test_equity_or_specific_interest_cannot_deduct_subsidiary_debt_again(index):
    case = holding_case()
    parts = case["methods"][-1]["inputs"]["holdings"]
    parts[index]["bridge"] = parts[0]["bridge"]
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize(
    ("key", "value"),
    [("ownership", "alpha-share"), ("rights_adjustment", "alpha-rights")],
)
def test_already_valued_interest_cannot_be_scaled_or_adjusted_again(key, value):
    case = holding_case()
    case["methods"][-1]["inputs"]["holdings"][2][key] = value
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("valuation_date", "2025-12-31"),
        ("currency", "CHF"),
        ("source_ids", ["missing-source"]),
        ("ownership_denominator_id", None),
    ],
)
def test_part_basis_requires_matching_date_currency_sources_and_denominator(
    field, value
):
    case = holding_case()
    case["methods"][-1]["inputs"]["holdings"][0]["basis"][field] = value
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize(
    "duplicate_kind",
    ["part-id", "interest-id", "parent-input", "elimination-id", "elimination-amount"],
)
def test_duplicate_declared_identities_and_adjustments_are_rejected(duplicate_kind):
    case = holding_case()
    args = case["methods"][-1]["inputs"]
    if duplicate_kind == "part-id":
        args["holdings"][1]["id"] = "alpha"
    elif duplicate_kind == "interest-id":
        args["holdings"][1]["basis"].update(
            entity_id="alpha", interest_id="alpha-interest"
        )
    elif duplicate_kind == "parent-input":
        args["parent_assets"].append("parent-debt")
    else:
        duplicate = deepcopy(args["eliminations"][0])
        if duplicate_kind == "elimination-id":
            duplicate["amount_input"] = "flow"
        else:
            duplicate["id"] = "second-elimination"
        args["eliminations"].append(duplicate)
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize(
    ("share", "denominator", "expected"),
    [
        ("0.5", "common-equity", "blocked"),
        ("0.4", "common-equity", "ready_for_professional_review"),
        ("0.5", "other-class", "ready_for_professional_review"),
    ],
)
def test_aggregate_ownership_checks_only_the_explicit_entity_denominator(
    share, denominator, expected
):
    case = holding_case()
    set_amount(case, "beta-share", share)
    case["methods"][-1]["inputs"]["holdings"][1]["basis"].update(
        entity_id="alpha", ownership_denominator_id=denominator
    )
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("affected_input_ids", ["flow"]),
        ("affected_input_ids", ["alpha-share"]),
        ("amount_input", "parent-tax"),
        ("source_ids", ["missing"]),
    ],
)
def test_elimination_needs_included_money_independent_amount_and_evidence(field, value):
    case = holding_case()
    case["methods"][-1]["inputs"]["eliminations"][0][field] = value
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"


@pytest.mark.parametrize("record", ["parent", "part", "elimination", "source"])
def test_unconfirmed_holding_basis_or_source_remains_partial(record):
    case = holding_case()
    method = case["methods"][-1]
    target = {
        "parent": method["holding_basis"],
        "part": method["inputs"]["holdings"][0]["basis"],
        "elimination": method["inputs"]["eliminations"][0],
        "source": case["sources"][-1],
    }[record]
    target["status"] = "unverified" if record == "source" else "proposed"
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "partial"
    assert "holding-basis" in result["methods"][-1]["source_ids"]


@pytest.mark.parametrize(
    "field",
    [
        "parent_perimeter",
        "costs_basis",
        "tax_basis",
        "intragroup_basis",
        "overlap_review",
        "rights_scope",
    ],
)
def test_changed_holding_basis_invalidates_only_dependent_method_review(field):
    case = holding_case()
    prepared = build_valuation(case, FIXTURE)
    case["methods"][0]["review"] = review(prepared["methods"][0]["dependency_sha256"])
    case["methods"][-1]["review"] = review(prepared["methods"][-1]["dependency_sha256"])
    case["methods"][-1]["holding_basis"][field] += " Changed scope."
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["stale_review"] is True
    assert result["methods"][0]["status"] == "accepted_workpaper"


@pytest.mark.parametrize("record", ["rights", "elimination", "basis-source", "amount"])
def test_changed_holding_detail_invalidates_accepted_claim(record):
    case = holding_case()
    claim = claimed_case()["claims"][0]
    claim.update(
        id="holding-value",
        text="Synthetic holding equity 595 EUR.",
        calculation_ids=["holding/value"],
        values=[{"calculation_id": "holding/value", "value": "595", "unit": "EUR"}],
    )
    case["claims"] = [claim]
    prepared = build_valuation(case, FIXTURE)
    case["methods"][-1]["review"] = review(prepared["methods"][-1]["dependency_sha256"])
    claim_ready = build_valuation(case, FIXTURE)
    claim["review"] = review(claim_ready["claims"][0]["dependency_sha256"])
    if record == "rights":
        case["methods"][-1]["inputs"]["holdings"][0]["basis"][
            "rights_basis"
        ] += " Changed."
    elif record == "elimination":
        case["methods"][-1]["inputs"]["eliminations"][0]["reason"] += " Changed."
    elif record == "basis-source":
        case["sources"][-1]["description"] += " Revised provenance."
    else:
        set_amount(case, "alpha-value", "1010")
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["stale_review"] is True
    assert result["claims"][0]["status"] != "accepted_workpaper"


def test_explicit_empty_parent_lists_and_no_elimination_are_not_filled_automatically():
    case = holding_case()
    args = case["methods"][-1]["inputs"]
    args.update(parent_assets=[], parent_liabilities=[], eliminations=[])
    set_amount(case, "parent-costs", "0")
    set_amount(case, "parent-tax", "0")
    result = build_valuation(case, FIXTURE)
    value = next(
        row["value"] for row in result["calculations"] if row["id"] == "holding/value"
    )
    assert Decimal(value) == Decimal("715")


@pytest.mark.parametrize(
    "missing_or_extra",
    [
        "holding_basis",
        "empty-parts",
        "bridge",
        "rights",
        "unknown-type",
        "parent-bridge",
        "timing",
    ],
)
def test_holding_requires_its_explicit_shape_without_an_extra_parent_bridge(
    missing_or_extra,
):
    case = holding_case()
    method = case["methods"][-1]
    if missing_or_extra == "holding_basis":
        del method["holding_basis"]
    elif missing_or_extra == "empty-parts":
        method["inputs"]["holdings"] = []
    elif missing_or_extra in {"bridge", "rights"}:
        del method["inputs"]["holdings"][0][
            "bridge" if missing_or_extra == "bridge" else "rights_adjustment"
        ]
    elif missing_or_extra == "unknown-type":
        method["inputs"]["holdings"][0]["value_type"] = "consolidated-equity"
    elif missing_or_extra == "parent-bridge":
        method["bridge"] = method["inputs"]["holdings"][0]["bridge"]
    else:
        method["timing"] = {}
    result = build_valuation(case, FIXTURE)
    assert result["methods"][-1]["status"] == "blocked"
    assert result["methods"][0]["status"] == "ready_for_professional_review"


def test_holding_rejects_plan_fcff_as_a_part_value(tmp_path):
    case = holding_case(planning_case(tmp_path))
    shutil.copyfile(FIXTURE / "holding-sotp.txt", tmp_path / "holding-sotp.txt")
    case["methods"][-1]["inputs"]["holdings"][0]["value"] = "flow"
    result = build_valuation(case, tmp_path, replay_parent=tmp_path / "replay")
    assert result["methods"][-1]["status"] == "blocked"
    assert "cannot be relabelled" in result["methods"][-1]["reason"]


def test_holding_export_links_parts_and_eliminations_and_keeps_prose_literal(tmp_path):
    from openpyxl import load_workbook

    case = holding_case()
    case["methods"][-1]["holding_basis"][
        "parent_perimeter"
    ] = '=HYPERLINK("https://example.org")<script>alert(1)</script>'
    result = build_valuation(case, FIXTURE)
    output = tmp_path / "holding"
    write_package(result, FIXTURE, output)
    workbook = load_workbook(output / "valuation_workbook.xlsx")
    assert workbook["Base holding"]["D2"].data_type == "s"
    assert workbook["Partecipazioni"]["D2"].data_type == "f"
    assert workbook["Eliminazioni"]["C2"].data_type == "f"
    assert "&lt;script&gt;alert" in compile_html(result)
    assert "<script>alert" not in compile_html(result)
    assert read_json(output / "valuation.json") == result


def test_holding_workflow_uses_real_archive_receipts(tmp_path, record_property):
    case_path, context = prepare_archive_run(
        tmp_path,
        supplied_case=holding_case(),
        source_files=[FIXTURE / "evidence.txt", FIXTURE / "holding-sotp.txt"],
    )
    output = run_valuation.run_case(case_path, context)
    result = read_json(Path(output["output_dir"]) / "valuation.json")
    assert result["methods"][-1]["status"] == "ready_for_professional_review"
    assert result["methods"][-1]["value_type"] == "equity"
    record_property("holding_output", output["output_dir"])
