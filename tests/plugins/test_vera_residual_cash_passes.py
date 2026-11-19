"""Independent synthetic populations; no client IDs or data-dependent decisions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "plugins/journal-bank-reconciliation/scripts"
    ),
)
import bank_first as bf
from local_cash_links import review_population


@pytest.fixture(autouse=True)
def source_imports(monkeypatch):
    monkeypatch.syspath_prepend(
        str(
            Path(__file__).resolve().parents[2]
            / "plugins/journal-bank-reconciliation/scripts"
        )
    )


REL = dict(
    relationship_shape="many_to_many",
    default_currency="EUR",
    default_unit="money",
    default_entity_ref="synthetic",
    direction_policy="same_sign",
)


def row(i, amount, day="2026-05-12", **kw):
    return dict(
        transaction_id=i,
        amount_signed=amount,
        transaction_date=day,
        description="Bank fee",
        **kw,
    )


def admit(b, j, **kw):
    return bf.admission(b, j, REL, local_matches=[], **kw)


def test_same_day_priority_and_model_population():
    b = [row("b", "-2.75")]
    j = [row("j", "-2.75"), row("later", "-2.75", "2026-05-13")]
    a = admit(b, j)
    assert a["sure"][0]["journal_ids"] == ["j"]
    assert review_population(b, j, a) == ([], [j[1]])


def test_equal_fee_group_is_group_not_arbitrary_pairs():
    b = [row("b1", "-4.20"), row("b2", "-4.20")]
    j = [row("j1", "-4.20"), row("j2", "-4.20")]
    a = admit(b, j)
    assert len(a["sure"]) == 1
    assert set(a["sure"][0]["bank_ids"]) == {"b1", "b2"}
    assert set(a["sure"][0]["journal_ids"]) == {"j1", "j2"}
    assert a["sure"][0]["difference"] == "0.00"


@pytest.mark.parametrize(
    "change",
    [
        dict(currency="USD"),
        dict(entity_ref="other"),
        dict(unit="units"),
        dict(party_ref="other"),
        dict(reference="other"),
    ],
)
def test_conflicting_scope_or_identity_is_not_locally_consumed(change):
    b = row("b", "-7.43", party_ref="customer", reference="invoice")
    j = row(
        "j", "-7.43", **dict(dict(party_ref="customer", reference="invoice"), **change)
    )
    assert not admit([b], [j])["sure"]


@pytest.mark.parametrize(
    "b,j",
    [
        ([row("b", "-3")], [row("j", "3")]),
        ([row("b", "-3", "invalid")], [row("j", "-3", "invalid")]),
        ([row("b", "0")], [row("j", "0")]),
        ([row("b1", "-3"), row("b2", "-3")], [row("j", "-3")]),
    ],
)
def test_ambiguous_or_invalid_rows_remain_unresolved(b, j):
    assert not admit(b, j)["sure"]


def test_aggregates_are_candidates_not_allocations():
    a = admit([row("b1", "-8.12"), row("b2", "-2.28")], [row("j", "-10.40")])
    assert not a["sure"]
    assert a["unresolved_bank_ids"] == ["b1", "b2"]
    assert a["probable_candidates"][0]["journal_ids"] == ["j"]
    assert (
        a["probable_candidates"][0]["rule_id"]
        == "residual_same_day_subset_candidate.v1"
    )


def test_competing_aggregates_are_all_preserved():
    a = admit(
        [row("a", "-1"), row("b", "-2"), row("c", "-1"), row("d", "-2")],
        [row("j", "-3")],
    )
    assert not a["sure"]
    assert len(a["probable_candidates"]) == 4


def test_nonfee_duplicates_are_not_consumed():
    b = [
        dict(row("a", "-4"), description="Shop"),
        dict(row("b", "-4"), description="Shop"),
    ]
    assert not admit(b, [row("j1", "-4"), row("j2", "-4")])["sure"]


def test_legacy_replay_does_not_gain_new_matches():
    assert not admit([row("b", "-8")], [row("j", "-8")], local_evidence_version=2)[
        "sure"
    ]


def test_existing_allocations_never_reused():
    a = bf.admission(
        [row("old", "-5"), row("new", "-5")],
        [row("j", "-5")],
        REL,
        local_matches=[dict(bank_transaction_id="old", journal_transaction_id="j")],
    )
    assert len(a["sure"]) == 1
    assert a["unresolved_bank_ids"] == ["new"]


def test_accounting_review_retains_cash_links_without_claiming_treatment():
    a = admit([row("b", "-8")], [row("j", "-8")], purpose="bank_accounting")
    assert a["sure"][0]["cash_only"] is False


@pytest.mark.parametrize(
    "amount,currency,entity",
    [
        ("-12.37", "GBP", "company-a"),
        ("412.09", "USD", "company-b"),
        ("-0.35", "EUR", "company-c"),
    ],
)
def test_independent_amounts_and_scopes_link_without_case_constants(
    amount, currency, entity
):
    a = admit(
        [row("source", amount, currency=currency, entity_ref=entity)],
        [row("target", amount, currency=currency, entity_ref=entity)],
    )
    assert a["sure"][0]["journal_ids"] == ["target"]


@pytest.mark.parametrize(
    "reverse_bank,reverse_journal", [(False, True), (True, False), (True, True)]
)
def test_source_order_does_not_change_group_membership(reverse_bank, reverse_journal):
    b = [row("b1", "-6.18"), row("b2", "-6.18")]
    j = [row("j1", "-6.18"), row("j2", "-6.18")]
    a = admit(b[::-1] if reverse_bank else b, j[::-1] if reverse_journal else j)
    assert set(a["sure"][0]["bank_ids"]) == {"b1", "b2"}
    assert set(a["sure"][0]["journal_ids"]) == {"j1", "j2"}


def test_reverse_and_three_row_aggregates_are_not_hard_coded():
    a = admit(
        [row("sum", "-16.74")],
        [row("a", "-10.12"), row("b", "-4.13"), row("c", "-2.49")],
    )
    assert not a["sure"]
    assert a["probable_candidates"][0]["journal_ids"] == ["a", "b", "c"]


def test_partial_fee_count_does_not_hide_unposted_fees():
    a = admit(
        [row("a", "-4.19"), row("b", "-4.19"), row("c", "-4.19")],
        [row("x", "-4.19"), row("y", "-4.19")],
    )
    assert not a["sure"]
    assert set(a["unresolved_bank_ids"]) == {"a", "b", "c"}
