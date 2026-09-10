"""Behavioral treasury cases: updates, corrections and preserved decisions."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/treasury-forecast/scripts"
sys.path.insert(0, str(SCRIPTS))
import treasury_core as core


def item(key: str, amount: str, due: str, side: str = "receivable") -> dict:
    return {
        "item_id": key,
        "party_id": f"party-{key}",
        "party_name": f"Synthetic {key}",
        "side": side,
        "document_type": "TD01",
        "document_number": key,
        "document_date": "2026-09-01",
        "installment": "1",
        "due_date": due,
        "amount": amount,
        "replaces_flow_id": "",
    }


def first() -> dict:
    return {
        "schema_version": "vera.treasury_inputs.v1",
        "client_id": "client-a",
        "engagement_id": "engagement-a",
        "company_id": "company-a",
        "company_name": "Synthetic company",
        "currency": "EUR",
        "as_of": "2026-09-10",
        "horizon_end": "2026-10-02",
        "coverage": "All cash events in the synthetic case; no financing.",
        "accounts": [{"account_id": "bank-a", "balance": "40000.00"}],
        "bank_movements": [],
        "allocations": [],
        "adjustments": [],
        "open_items": [
            item("C101", "50000.00", "2026-09-15"),
            item("C102", "10000.00", "2026-09-22"),
            item("S201", "65000.00", "2026-09-16", "payable"),
        ],
        "planned_flows": [
            {
                "flow_id": "PAYROLL-SEP",
                "side": "payable",
                "amount": "20000.00",
                "expected_date": "2026-09-30",
                "description": "September payroll",
                "basis": "Supplied payroll schedule",
            }
        ],
    }


def accept(
    data: dict, previous: dict | None = None, decisions: dict | None = None
) -> dict:
    proposal = core.build_forecast(data, previous=previous, decisions=decisions)
    review = {
        "proposal_sha256": proposal["proposal_sha256"],
        "reviewer_ref": "test-reviewer",
        "reviewed_at": data["as_of"],
        "conclusion": "Synthetic assumptions reviewed for the test.",
    }
    return core.build_forecast(
        data, previous=previous, decisions=decisions, review=review
    )


def second() -> dict:
    data = first()
    data["as_of"] = "2026-09-18"
    data["accounts"][0]["balance"] = "5000.00"
    data["bank_movements"] = [
        {
            "movement_id": "BANK01",
            "account_id": "bank-a",
            "date": "2026-09-15",
            "amount": "30000.00",
            "description": "Partial C101 receipt",
        },
        {
            "movement_id": "BANK02",
            "account_id": "bank-a",
            "date": "2026-09-16",
            "amount": "-65000.00",
            "description": "S201 paid",
        },
    ]
    data["allocations"] = [
        {
            "allocation_id": "A1",
            "movement_id": "BANK01",
            "target_type": "item",
            "target_id": "C101",
            "amount": "30000.00",
        },
        {
            "allocation_id": "A2",
            "movement_id": "BANK02",
            "target_type": "item",
            "target_id": "S201",
            "amount": "65000.00",
        },
    ]
    data["adjustments"] = [
        {
            "adjustment_id": "CN01",
            "item_id": "C102",
            "date": "2026-09-17",
            "amount": "-3000.00",
            "kind": "credit_note",
            "evidence_ref": "supplied-credit-note",
        }
    ]
    data["open_items"] = [
        item("C101", "20000.00", "2026-09-15"),
        item("C102", "7000.00", "2026-09-22"),
        item("S202", "8000.00", "2026-09-24", "payable"),
    ]
    return data


def delayed() -> dict:
    return {
        "item:C101": {
            "expected_date": "2026-10-02",
            "basis": "Client supplied expected receipt date",
        }
    }


def third() -> dict:
    data = first()
    data.update(
        as_of="2026-10-03", horizon_end="2026-11-02", open_items=[], planned_flows=[]
    )
    data["accounts"][0]["balance"] = "4000.00"
    data["bank_movements"] = [
        {
            "movement_id": "B3",
            "account_id": "bank-a",
            "date": "2026-09-22",
            "amount": "7000.00",
            "description": "C102 receipt",
        },
        {
            "movement_id": "B4",
            "account_id": "bank-a",
            "date": "2026-09-24",
            "amount": "-8000.00",
            "description": "S202 paid",
        },
        {
            "movement_id": "B5",
            "account_id": "bank-a",
            "date": "2026-09-30",
            "amount": "-20000.00",
            "description": "Payroll",
        },
        {
            "movement_id": "B6",
            "account_id": "bank-a",
            "date": "2026-10-02",
            "amount": "20000.00",
            "description": "C101 residual receipt",
        },
    ]
    data["allocations"] = [
        {
            "allocation_id": "A3",
            "movement_id": "B3",
            "target_type": "item",
            "target_id": "C102",
            "amount": "7000.00",
        },
        {
            "allocation_id": "A4",
            "movement_id": "B4",
            "target_type": "item",
            "target_id": "S202",
            "amount": "8000.00",
        },
        {
            "allocation_id": "A5",
            "movement_id": "B5",
            "target_type": "plan",
            "target_id": "PAYROLL-SEP",
            "amount": "20000.00",
        },
        {
            "allocation_id": "A6",
            "movement_id": "B6",
            "target_type": "item",
            "target_id": "C101",
            "amount": "20000.00",
        },
    ]
    return data


def test_first_forecast_shows_supplied_cash_schedule_without_automatic_acceptance() -> (
    None
):
    result = core.build_forecast(first())
    assert result["status"] == "draft_for_review"
    assert result["daily"][-1]["closing_cash"] == "15000.00"
    assert result["minimum_daily_cash"] == "15000.00"
    assert result["first_negative_day"] is None


def test_update_distinguishes_partial_receipt_credit_note_and_new_payment() -> None:
    previous = accept(first())
    result = core.build_forecast(second(), previous=previous, decisions=delayed())
    september = next(row for row in result["daily"] if row["date"] == "2026-09-30")
    assert result["opening_cash"] == "5000.00"
    assert september["closing_cash"] == "-16000.00"
    assert result["daily"][-1]["closing_cash"] == "4000.00"
    assert result["first_negative_day"] == "2026-09-30"
    assert result["non_cash_adjustments"] == {"C102": "-3000.00"}
    assert result["comparison"]["closing_variance"] == "-11000.00"
    assert "item:S201" not in {event["event_id"] for event in result["events"]}


def test_third_update_removes_settled_residuals_without_adding_receipts_again() -> None:
    previous = accept(second(), accept(first()), delayed())
    result = core.build_forecast(third(), previous=previous)
    assert result["opening_cash"] == "4000.00"
    assert result["daily"][-1]["closing_cash"] == "4000.00"
    assert result["events"] == []
    assert result["comparison"] is None


def test_new_plan_settled_in_same_update_is_not_forecast_again() -> None:
    original = first()
    original["accounts"][0]["balance"] = "1000.00"
    original["open_items"] = []
    original["planned_flows"] = []
    previous = accept(original)
    data = copy.deepcopy(original)
    data["as_of"] = "2026-09-18"
    data["accounts"][0]["balance"] = "900.00"
    data["bank_movements"] = [
        {
            "movement_id": "M1",
            "account_id": "bank-a",
            "date": "2026-09-18",
            "amount": "-100.00",
            "description": "New plan paid",
        }
    ]
    data["planned_flows"] = [
        {
            "flow_id": "P1",
            "side": "payable",
            "amount": "100.00",
            "expected_date": "2026-09-30",
            "description": "New supplied plan",
            "basis": "Synthetic plan",
        }
    ]
    data["allocations"] = [
        {
            "allocation_id": "A1",
            "movement_id": "M1",
            "target_type": "plan",
            "target_id": "P1",
            "amount": "100.00",
        }
    ]

    result = core.build_forecast(data, previous=previous)

    assert result["daily"][-1]["closing_cash"] == "900.00"
    assert result["events"] == []


def test_comparison_uses_common_horizon_and_separates_extension() -> None:
    original = first()
    original["horizon_end"] = "2026-09-30"
    previous = accept(original)
    result = core.build_forecast(second(), previous=previous, decisions=delayed())
    assert result["comparison"]["through"] == "2026-09-30"
    assert result["comparison"]["closing_variance"] == "-31000.00"
    assert result["comparison"]["opening_variance"] == "-20000.00"
    assert result["comparison"]["horizon_extended"] is True


def test_hypothetical_earlier_collection_preserves_baseline() -> None:
    baseline = accept(second(), accept(first()), delayed())
    before = copy.deepcopy(baseline)
    result = core.build_scenario(baseline, {"item:C101": "2026-09-25"})
    assert result["minimum_daily_cash"] == "4000.00"
    assert result["status"] == "hypothetical"
    assert baseline == before


def test_expired_date_prevents_acceptance_and_does_not_invent_a_new_date() -> None:
    previous = accept(first())
    proposal = core.build_forecast(second(), previous=previous)
    assert proposal["calculation_complete"] is False
    assert proposal["issues"][0]["event_id"] == "item:C101"
    with pytest.raises(core.TreasuryError, match="Unresolved dates"):
        accept(second(), previous)


def test_reviewed_expected_date_survives_evidenced_partial_receipt() -> None:
    previous = accept(first(), decisions=delayed())
    result = core.build_forecast(second(), previous=previous)
    event = next(row for row in result["events"] if row["event_id"] == "item:C101")
    assert event["amount"] == "20000.00"
    assert event["expected_date"] == "2026-10-02"
    assert event["decision_origin"] == "retained"


def test_changed_due_date_reopens_an_earlier_professional_override() -> None:
    previous = accept(first(), decisions=delayed())
    data = second()
    data["open_items"][0]["due_date"] = "2026-09-25"
    result = core.build_forecast(data, previous=previous)
    assert result["issues"][0]["event_id"] == "item:C101"
    assert result["calculation_complete"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "missing_payment",
        "missing_credit_note",
        "cash_duplicate",
        "balance",
        "identity",
        "new_id",
        "old_movement",
        "wrong_side",
        "missing_plan",
    ],
)
def test_inconsistent_update_cannot_be_accepted(fault: str) -> None:
    previous = accept(first())
    data = second()
    if fault == "missing_payment":
        data["allocations"].pop()
    elif fault == "missing_credit_note":
        data["adjustments"] = []
    elif fault == "cash_duplicate":
        data["allocations"].append(dict(data["allocations"][0], allocation_id="repeat"))
    elif fault == "balance":
        data["accounts"][0]["balance"] = "6000.00"
    elif fault == "identity":
        data["open_items"][0]["party_id"] = "different-party"
    elif fault == "new_id":
        data["open_items"][0]["item_id"] = "different-id"
    elif fault == "old_movement":
        data["bank_movements"][0]["date"] = "2026-09-10"
    elif fault == "wrong_side":
        data["allocations"][0]["target_id"] = "S202"
    else:
        data["planned_flows"] = []
    with pytest.raises(core.TreasuryError):
        core.build_forecast(data, previous=previous, decisions=delayed())


@pytest.mark.parametrize(
    "value", ["1.001", "1,20", "NaN", "Infinity", "1e4", 100, True, ""]
)
def test_ambiguous_or_inexact_money_is_rejected(value: object) -> None:
    with pytest.raises(core.TreasuryError):
        core.money(value)


def test_input_order_duplicate_key_and_repeated_run() -> None:
    data = first()
    before = copy.deepcopy(data)
    original = core.build_forecast(data)
    repeated = core.build_forecast(data)
    assert original == repeated
    assert data == before
    data["open_items"].append(copy.deepcopy(data["open_items"][0]))
    with pytest.raises(core.TreasuryError, match="Duplicate"):
        core.build_forecast(data)


def test_stale_review_cannot_accept_changed_dates() -> None:
    data = first()
    proposal = core.build_forecast(data)
    review = {
        "proposal_sha256": proposal["proposal_sha256"],
        "reviewer_ref": "test",
        "reviewed_at": data["as_of"],
        "conclusion": "Accepted",
    }
    with pytest.raises(core.TreasuryError, match="Stale"):
        core.build_forecast(data, decisions=delayed(), review=review)


def test_predecessor_must_be_accepted_unchanged_and_same_client() -> None:
    unreviewed = core.build_forecast(first())
    with pytest.raises(core.TreasuryError, match="accepted"):
        core.build_forecast(second(), previous=unreviewed)
    changed = accept(first())
    changed["opening_cash"] = "0.00"
    with pytest.raises(core.TreasuryError, match="digest"):
        core.build_forecast(second(), previous=changed)
    alien = second()
    alien["client_id"] = "client-b"
    with pytest.raises(core.TreasuryError, match="another"):
        core.build_forecast(alien, previous=accept(first()))


def test_invoice_replaces_estimate_once_and_relationship_survives_later_updates() -> (
    None
):
    data = first()
    data["planned_flows"].append(
        {
            "flow_id": "INVESTMENT",
            "side": "payable",
            "amount": "8000.00",
            "expected_date": "2026-09-24",
            "description": "Equipment",
            "basis": "Supplied purchase plan",
        }
    )
    previous = accept(data)
    update = second()
    update["open_items"][-1]["replaces_flow_id"] = "INVESTMENT"
    current = accept(update, previous, delayed())
    assert current["replacements"] == {"INVESTMENT": "S202"}
    assert sum(row["event_id"] == "item:S202" for row in current["events"]) == 1
    assert all(row["event_id"] != "plan:INVESTMENT" for row in current["events"])
    result = core.build_forecast(third(), previous=current)
    assert result["events"] == []
    assert result["replacements"] == {"INVESTMENT": "S202"}


def test_non_invoice_bank_charge_changes_actual_cash_without_inventing_an_allocation() -> (
    None
):
    data = second()
    data["accounts"][0]["balance"] = "4900.00"
    data["bank_movements"].append(
        {
            "movement_id": "FEE",
            "account_id": "bank-a",
            "date": "2026-09-17",
            "amount": "-100.00",
            "description": "Bank charge",
        }
    )
    result = core.build_forecast(data, previous=accept(first()), decisions=delayed())
    assert result["opening_cash"] == "4900.00"
    assert result["evidence_notes"][0]["id"] == "FEE"
    assert result["evidence_notes"][0]["amount"] == "100.00"


def test_fixture_json_roundtrip_is_lossless(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    record = accept(first())
    path.write_text(json.dumps(record))
    restored = json.loads(path.read_text())
    core.validate_record(restored, accepted=True)
    assert restored == record
