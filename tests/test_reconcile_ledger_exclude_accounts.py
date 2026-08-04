import sys
from datetime import date
from pathlib import Path
from typing import Any

# Ensure top-level packages under src resolve without replacing shared modules.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.check_statements import (
    Transaction,
    _filter_accounts,
    load_ledger_files,
    reconcile_transactions,
)


class CountingDict(dict):
    def __init__(self, *args, counter: list[int], **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = counter

    def get(self, key, default=None):
        if key in {"account_id", "account_identifier"}:
            self.counter[0] += 1
        return super().get(key, default)


def _ledger_tx(
    account: Any, amount: float, counter: list[int] | None = None
) -> Transaction:
    meta: dict[str, Any] = {"account_id": account}
    if counter is not None:
        meta = CountingDict(meta, counter=counter)
    return Transaction(
        date=date(2024, 1, 1),
        amount=amount,
        description="",
        beneficiary="Same Co" if amount == 10.0 else "Other",
        metadata=meta,
    )


def test_reconcile_transactions_filters_once_when_pre_filtered() -> None:
    bank = [
        Transaction(
            date=date(2024, 1, 1), amount=10.0, description="", beneficiary="Same Co"
        ),
    ]
    counter1 = [0]
    ledger_all1 = [_ledger_tx("A", 10.0, counter1), _ledger_tx("B", 20.0, counter1)]
    ledger1 = _filter_accounts(ledger_all1, ["B"])
    counter1[0] = 0
    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger1,
        ledger_exclude_accounts=["B"],
        ledger_pre_filtered=True,
    )
    assert len(matched) == 1
    assert matched[0][:2] == (0, 0)
    assert matched[0][2] in {"exact", "beneficiary"}
    assert unmatched_bank == []
    assert unmatched_ledger == []
    assert counter1[0] == 0

    counter2 = [0]
    ledger_all2 = [_ledger_tx("A", 10.0, counter2), _ledger_tx("B", 20.0, counter2)]
    ledger2 = _filter_accounts(ledger_all2, ["B"])
    counter2[0] = 0
    reconcile_transactions(
        bank,
        ledger2,
        ledger_exclude_accounts=["B"],
        ledger_pre_filtered=False,
    )
    assert counter2[0] == len(ledger2)


def test_filter_accounts_case_insensitive_and_spaces() -> None:
    ledger_all = [
        _ledger_tx(" Acct1 ", 10.0),
        _ledger_tx("b2", 20.0),
        _ledger_tx("c3", 30.0),
    ]
    filtered = _filter_accounts(ledger_all, ["acct1", " B2 "])
    assert [tx.metadata["account_id"] for tx in filtered] == ["c3"]


def test_filter_accounts_retains_non_string_ids() -> None:
    ledger_all = [_ledger_tx(100, 10.0), _ledger_tx("A", 20.0)]
    filtered = _filter_accounts(ledger_all, [100])
    assert [tx.metadata["account_id"] for tx in filtered] == ["A"]


def test_load_ledger_files_preserves_account_description() -> None:
    csv = (
        "date,description,account,account description,amount\n"
        "01/01/2024,foo, A1 ,Cash,10\n"
    ).encode()
    txns = load_ledger_files([("ledger.csv", csv)])
    assert txns[0].metadata["account_desc"] == "Cash"
