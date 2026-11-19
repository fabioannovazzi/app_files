"""Model-authored discovery has bounded data-only capabilities, never I/O."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
sys.path.insert(0, str(SCRIPTS))
from reconciliation_expression import ExpressionLimit, evaluate_candidates

BANK = [dict(transaction_id="bank-a", cents=-1234, reference="PAY 12")]
JOURNAL = [dict(transaction_id="journal-a", cents=-1234, reference="PAY12")]
RULE = """[{'bank_ids':[b['transaction_id']], 'journal_ids':[j['transaction_id']]}
for b in bank for j in journal
if b['cents'] == j['cents'] and b['reference'].replace(' ', '').casefold() == j['reference'].casefold()]"""


def test_general_rule_returns_candidates_for_supplied_rows():
    assert evaluate_candidates(RULE, BANK, JOURNAL) == [
        dict(bank_ids=["bank-a"], journal_ids=["journal-a"])
    ]


@pytest.mark.parametrize(
    "rule",
    [
        "__import__('os').system('id')",
        "open('/tmp/secret').read()",
        "bank.__class__.__mro__",
        "bank.clear()",
        "[x for x in range(1000000000)]",
        "'x' * 1000000000",
        "2 ** 1000000000",
        "(lambda: 1)()",
        "[{'bank_ids':['bank-a']}]",
    ],
)
def test_capability_escape_and_case_specific_rules_are_rejected(rule):
    with pytest.raises((ExpressionLimit, ValueError)):
        evaluate_candidates(rule, BANK, JOURNAL)


def test_operation_limit_stops_combinatorial_work():
    with pytest.raises(ExpressionLimit, match="budget"):
        evaluate_candidates(
            "[{} for b in bank for j in journal]",
            BANK * 100,
            JOURNAL * 100,
            max_steps=100,
        )


def test_candidate_count_is_bounded():
    with pytest.raises(ExpressionLimit, match="collection"):
        evaluate_candidates("[{} for b in bank]", BANK * 10, JOURNAL, max_items=3)


def test_replacement_cannot_allocate_an_expanding_string():
    with pytest.raises(ExpressionLimit, match="Expanding"):
        evaluate_candidates(
            "[{'bank_ids': [b['reference'].replace('', '   ')]} for b in bank]",
            BANK,
            JOURNAL,
        )


def test_discovery_does_not_mutate_source_rows():
    before = repr((BANK, JOURNAL))
    evaluate_candidates(RULE, BANK, JOURNAL)
    assert repr((BANK, JOURNAL)) == before


@pytest.mark.parametrize(
    "rule",
    [
        "[{'bank_ids':[bank[0]['transaction_id']], 'journal_ids':[journal[0]['transaction_id']]}]",
        "[{'bank_ids':[b['transaction_id']], 'journal_ids':[j['transaction_id']]} for b in bank for j in journal if b['cents'] == -1234]",
        "[{'bank_ids':[b['transaction_id']], 'journal_ids':[j['transaction_id']]} for b in bank for j in journal if b['reference'] == 'PAY 12']",
    ],
)
def test_case_specific_amount_counterparty_or_position_is_rejected(rule):
    with pytest.raises(ExpressionLimit):
        evaluate_candidates(rule, BANK, JOURNAL)


def test_computed_positional_selection_cannot_bypass_general_rule_boundary():
    with pytest.raises(ExpressionLimit, match="named source fields"):
        evaluate_candidates("[bank[len(bank)-len(bank)]]", BANK, JOURNAL)
