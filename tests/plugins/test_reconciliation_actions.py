"""Candidate tools preserve ambiguity rather than committing arithmetic guesses."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
sys.path.insert(0, str(SCRIPTS))
from reconciliation_actions import discover

REL = dict(default_currency="EUR", default_unit="money", default_entity_ref="fixture")


def row(i, a, **kw):
    return dict(
        transaction_id=i,
        amount_signed=a,
        transaction_date="2026-06-11",
        description="source",
        **kw,
    )


def test_date_shift_preserves_competing_candidates():
    b = [row("b", "-18.64")]
    j = [
        {**row("j1", "-18.64"), "transaction_date": "2026-06-12"},
        {**row("j2", "-18.64"), "transaction_date": "2026-06-13"},
    ]
    result = discover("date_window", b, j, REL)
    assert len(result["candidates"]) == 2
    assert result["accepted_matches"] == 0


def test_reference_normalization_preserves_digits_and_does_not_accept_mismatched_sums():
    result = discover(
        "reference_normalized",
        [row("b", "-18.64", reference="AB-0012")],
        [
            row("j", "-19", reference="ab 0012"),
            row("other", "-18.64", reference="AB12"),
        ],
        REL,
    )
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["journal_ids"] == ["j"]
    assert (
        result["candidates"][0]["bank_cents"]
        != result["candidates"][0]["journal_cents"]
    )
    assert result["accepted_matches"] == 0


def test_net_settlement_is_candidate_with_explicit_signed_amounts():
    result = discover(
        "subset_sum",
        [row("b", "97.50")],
        [row("gross", "100"), row("fee", "-2.50")],
        REL,
    )
    assert result["candidates"][0]["journal_ids"] == ["fee", "gross"]
    assert result["candidates"][0]["bank_cents"] == 9750
    assert result["candidates"][0]["journal_cents"] == 9750
    assert result["accepted_matches"] == 0


def test_reversal_is_not_ledger_reconciliation():
    result = discover("reversals", [row("a", "-21.17"), row("b", "21.17")], [], REL)
    assert result["candidates"][0]["journal_ids"] == []
    assert result["accepted_matches"] == 0


def test_scope_conflicts_are_excluded():
    result = discover(
        "date_window",
        [row("b", "-18.64", currency="GBP")],
        [row("j", "-18.64", currency="EUR")],
        REL,
    )
    assert result["candidates"] == []


def test_budget_is_visible_and_never_claims_absence():
    result = discover(
        "date_window",
        [row("b", "-18.64")],
        [row("j1", "-18.64"), row("j2", "-18.64")],
        REL,
        operations=1,
    )
    assert result["truncated"] is True
    assert result["search_is_exhaustive"] is False


def test_generated_rule_has_same_source_scope_boundary():
    expression = "[{'bank_ids':[b['transaction_id']], 'journal_ids':[j['transaction_id']]} for b in bank for j in journal if b['cents'] == j['cents']]"
    result = discover(
        "generated_expression",
        [row("b", "-18.64")],
        [row("j", "-18.64")],
        REL,
        expression=expression,
    )
    assert result["candidates"][0]["journal_ids"] == ["j"]
    assert result["accepted_matches"] == 0


@pytest.mark.parametrize(
    "expression",
    ["[{'bank_ids':['foreign'], 'journal_ids':['other']}]", "[{'write':'anything'}]"],
)
def test_generated_results_cannot_invent_sources_or_actions(expression):
    with pytest.raises(ValueError):
        discover(
            "generated_expression",
            [row("b", "-18.64")],
            [row("j", "-18.64")],
            REL,
            expression=expression,
        )
