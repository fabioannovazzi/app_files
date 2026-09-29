"""Synthetic arithmetic, review and change scenarios from the recovered proposal."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/scissione-guidata/scripts"))
from scissione_core import ScissioneError, build_revision, decimal, simple_exchange


def case() -> dict:
    return json.loads(
        (ROOT / "plugins/scissione-guidata/references/synthetic-case.json").read_text()
    )


def row(data: dict, key: str) -> dict:
    return next(item for item in data["records"] if item["id"] == key)


def review_request(revision: dict, ids: list[str] | None = None) -> dict:
    return {
        "revision_sha256": revision["revision_sha256"],
        "record_ids": ids if ids is not None else list(revision["fingerprints"]),
        "reviewer": "synthetic-reviewer",
        "role": "synthetic professional",
        "reviewed_at": "2026-09-29T19:00:00+02:00",
        "rationale": "Synthetic acceptance; no real professional approval",
    }


def accepted(data: dict | None = None) -> dict:
    data = data or case()
    draft = build_revision(data)
    inputs = [item["id"] for item in data["records"] if item["kind"] != "document"]
    calculated = build_revision(
        data, previous=draft, review=review_request(draft, inputs)
    )
    documents = [item["id"] for item in data["records"] if item["kind"] == "document"]
    return build_revision(
        data, previous=calculated, review=review_request(calculated, documents)
    )


def test_example_b_preserves_both_owners_and_four_value_bases():
    result = accepted()
    owners = result["schedule"]["owners"]
    assert owners[0]["economic_remaining"] == "420000.00"
    assert owners[0]["economic_transferred"] == "180000.00"
    assert owners[1]["economic_remaining"] == "280000.00"
    assert owners[1]["economic_transferred"] == "120000.00"
    assert owners[0]["shareholder_tax_cost"] is None
    assert result["schedule"]["allocations"][0]["tax"]["transferred"] == "120000"
    assert result["status"] == "prepared_for_review"
    assert result["legal_validation"] == "not_certified"


def test_unreviewed_draft_never_runs_the_calculation():
    result = build_revision(case())
    assert result["schedule"] == {}
    assert result["approvals"] == {}
    assert result["status"] == "partial"


def test_document_cannot_be_approved_before_its_schedule_is_generated():
    draft = build_revision(case())
    with pytest.raises(ScissioneError, match="document|Document"):
        build_revision(
            case(), previous=draft, review=review_request(draft, ["project"])
        )


@pytest.mark.parametrize("version,expected", [((3, 12, 0), 0), ((3, 11, 9), 2)])
def test_dependency_check_accepts_only_managed_runtime(monkeypatch, version, expected):
    spec = importlib.util.spec_from_file_location(
        "scissione_dependencies",
        ROOT / "plugins/scissione-guidata/scripts/check_dependencies.py",
    )
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker.sys, "version_info", version)
    assert checker.main([]) == expected


def test_t26_material_contract_missing_prevents_completion_despite_balanced_values():
    data = case()
    row(data, "contracts")["status"] = "unknown"
    result = build_revision(data)
    assert "Material evidence unknown: contracts" in result["issues"]
    assert result["status"] == "partial"


def test_unknown_dependency_cannot_be_hidden_by_approving_a_parent():
    data = case()
    row(data, "contracts")["status"] = "unknown"
    draft = build_revision(data)
    with pytest.raises(ScissioneError, match="Unknown or contested"):
        build_revision(
            data, previous=draft, review=review_request(draft, ["perimeter"])
        )


def test_t29_value_change_invalidates_dependent_approvals_and_keeps_history():
    previous = accepted()
    historical = copy.deepcopy(previous)
    data = case()
    row(data, "valuation")["data"].update(transferred="400000", remaining="600000")
    result = build_revision(data, previous=previous)
    assert result["change_impact"]["invalidated_approval_ids"] == [
        "calculation",
        "perimeter",
        "project",
        "valuation",
    ]
    assert "ownership" in result["approvals"]
    assert previous == historical
    assert result["schedule"] == {}


def test_t25_unrelated_rule_change_preserves_share_calculation_approval():
    data = case()
    tax = copy.deepcopy(row(data, "contracts"))
    tax.update(
        id="tax-rule",
        kind="rule",
        material=False,
        data={
            "state": "source_checked",
            "act": "Synthetic act",
            "article": "1",
            "paragraph": "1",
            "version": "v1",
            "scope": "Synthetic losses",
            "source_status": "original_checked",
            "effective_from": "2026-01-01",
            "applicable_from": "2026-01-01",
        },
    )
    data["records"].append(tax)
    previous = accepted(data)
    row(data, "tax-rule")["data"]["version"] = "v2"
    result = build_revision(data, previous=previous)
    assert result["change_impact"]["invalidated_approval_ids"] == ["tax-rule"]
    assert result["approvals"]["calculation"] == previous["approvals"]["calculation"]


@pytest.mark.parametrize("state", ["candidate", "withdrawn", "superseded"])
def test_parent_review_cannot_hide_an_unreviewable_rule(state):
    data = case()
    rule = copy.deepcopy(row(data, "contracts"))
    rule.update(
        id="rule",
        kind="rule",
        material=False,
        data={
            "state": state,
            "act": "Synthetic act",
            "article": "1",
            "paragraph": "1",
            "version": "v1",
            "scope": "Synthetic test",
            "source_status": "original_checked",
            "effective_from": None,
            "applicable_from": None,
        },
    )
    data["records"].append(rule)
    row(data, "calculation")["depends_on"].append("rule")
    draft = build_revision(data)
    with pytest.raises(ScissioneError, match="original checked source"):
        build_revision(
            data, previous=draft, review=review_request(draft, ["calculation"])
        )


def test_indirect_unreviewed_input_blocks_calculation_even_if_nonmaterial_alone():
    data = case()
    fact = copy.deepcopy(row(data, "contracts"))
    fact.update(id="extra-assumption", kind="fact", material=False)
    data["records"].append(fact)
    row(data, "calculation")["depends_on"].append("extra-assumption")
    draft = build_revision(data)
    selected = [
        r["id"]
        for r in data["records"]
        if r["kind"] != "document" and r["id"] != "extra-assumption"
    ]
    result = build_revision(
        data, previous=draft, review=review_request(draft, selected)
    )
    assert result["schedule"] == {}
    assert "Professional review pending: extra-assumption" in result["issues"]


def test_stale_review_is_rejected():
    draft = build_revision(case())
    request = review_request(draft)
    request["revision_sha256"] = "0" * 64
    with pytest.raises(ScissioneError, match="Stale review"):
        build_revision(case(), previous=draft, review=request)


def test_changed_calculation_engine_reopens_prior_reviews(monkeypatch):
    import scissione_core

    previous = accepted()
    monkeypatch.setattr(scissione_core, "ENGINE_VERSION", "next-test-version")
    result = build_revision(case(), previous=previous)
    assert result["approvals"] == {}
    assert result["schedule"] == {}
    assert previous["approvals"]["calculation"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("accounting", "IFRS"),
        ("jurisdiction", "CH"),
        ("operation", "scorporo"),
        ("beneficiary", "existing"),
    ],
)
def test_unsupported_routes_remain_explicit_without_oic_fallback(field, value):
    data = case()
    row(data, "route")["data"]["scope"][field] = value
    result = build_revision(data)
    assert result["status"] == "unsupported"
    assert result["schedule"] == {}


def test_t28_generated_dossier_does_not_establish_filing():
    result = accepted()
    assert result["filing_status"] == "not_performed"
    assert result["schedule"]["filing_status"] == "not_performed"


def test_t30_fractional_units_keep_all_owners_and_visible_residuals():
    data = case()
    row(data, "calculation")["data"]["new_units"] = "1"
    result = accepted(data)
    assert result["schedule"]["owners"][0]["unit_residual"] == "-0.40"
    assert result["schedule"]["owners"][1]["unit_residual"] == "0.40"
    assert len(result["schedule"]["owners"]) == 2
    assert result["status"] == "partial"


@pytest.mark.parametrize("value", [None, 0, 1.0, "NaN", "Infinity", "1e6"])
def test_missing_or_inexact_amount_is_not_coerced(value):
    with pytest.raises(ScissioneError):
        decimal(value)


def test_missing_tax_amount_stays_missing_and_partial():
    data = case()
    row(data, "inventory")["data"]["tax"]["transferred"] = None
    result = accepted(data)
    assert result["schedule"]["allocations"][0]["tax"]["transferred"] is None
    assert "Missing tax amount for inventory" in result["issues"]


def test_dependency_cycle_is_rejected():
    data = case()
    row(data, "route")["depends_on"] = ["calculation"]
    with pytest.raises(ScissioneError, match="Cyclic"):
        build_revision(data)


def test_t31_evidence_cannot_cross_entity_perimeter():
    data = case()
    row(data, "contracts")["entity_ids"] = ["scissa"]
    with pytest.raises(ScissioneError, match="outside the record perimeter"):
        build_revision(data)


def exchange(**overrides) -> dict:
    args = {
        "beneficiary_value": "600000",
        "transferred_value": "400000",
        "existing_units": "60000",
        "nominal_value": "1",
        "homogeneous_rights": True,
        "reciprocal_holdings": False,
        "own_shares": False,
        "separate_synergies": False,
        "cash_adjustment": False,
    }
    return simple_exchange(**(args | overrides))


def test_t06_exchange_a_separates_nominal_capital_from_economic_transfer():
    assert exchange() == {
        "new_units": "40000",
        "new_share": "0.4",
        "old_share": "0.6",
        "nominal_increase": "40000",
        "economic_transfer": "400000",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"homogeneous_rights": False},
        {"reciprocal_holdings": True},
        {"own_shares": True},
        {"separate_synergies": True},
        {"cash_adjustment": True},
        {"beneficiary_value": "0"},
        {"beneficiary_value": "-1"},
        {"transferred_value": "0"},
    ],
)
def test_t07_t08_exchange_rejects_unmet_assumptions(overrides):
    with pytest.raises(ScissioneError):
        exchange(**overrides)
