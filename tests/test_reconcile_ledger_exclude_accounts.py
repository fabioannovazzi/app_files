import sys
import types
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

# Stub out external modules used by ``check_statements_logic``. Only the parts
# required by this test are implemented.
parsers_module = types.ModuleType("parsers")
extractors_module = types.ModuleType("extractors")
extractors_module.extract_beneficiary = lambda x: ""
extractors_module.extract_references = lambda x: []
extractors_module.normalise_name = lambda x: x
parsers_module.extractors = extractors_module
sys.modules.setdefault("parsers", parsers_module)
sys.modules["parsers.extractors"] = extractors_module

statements_module = types.ModuleType("statements")
orchestrator_module = types.ModuleType("orchestrator")
orchestrator_module.StatementExtractor = object
statements_module.orchestrator = orchestrator_module
sys.modules.setdefault("statements", statements_module)
sys.modules["statements.orchestrator"] = orchestrator_module

finance_module = types.ModuleType("finance")
finance_module.__path__ = []  # mark as package

ledger_module = types.ModuleType("ledger")
ignore_patterns_module = types.ModuleType("ignore_patterns")
ignore_patterns_module.load_ignore_patterns = lambda path=None: []
ledger_module.ignore_patterns = ignore_patterns_module
finance_module.ledger = ledger_module

bank_statements_module = types.ModuleType("bank_statements")
bank_statements_module.__path__ = []

bank_ignore_patterns_module = types.ModuleType("ignore_patterns")
bank_ignore_patterns_module.DROP_PATTERNS = {}
bank_ignore_patterns_module.ALL_PATTERNS = {}
bank_statements_module.ignore_patterns = bank_ignore_patterns_module
finance_module.bank_statements = bank_statements_module
sys.modules.setdefault("finance", finance_module)
sys.modules["finance.ledger"] = ledger_module
sys.modules["finance.ledger.ignore_patterns"] = ignore_patterns_module
sys.modules["finance.bank_statements"] = bank_statements_module
sys.modules["finance.bank_statements.ignore_patterns"] = bank_ignore_patterns_module

from modules.check_statements.logic import build_ledger_account_map
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


def _ledger_tx(account: Any, amount: float, counter: list[int] | None = None) -> Transaction:
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
        Transaction(date=date(2024, 1, 1), amount=10.0, description="", beneficiary="Same Co"),
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


def test_load_ledger_files_and_ui_account_desc(monkeypatch: pytest.MonkeyPatch) -> None:
    csv = (
        "date,description,account,account description,amount\n"
        "01/01/2024,foo, A1 ,Cash,10\n"
    ).encode()
    txns = load_ledger_files([("ledger.csv", csv)])
    assert txns[0].metadata["account_desc"] == "Cash"

    mapping = build_ledger_account_map(txns)
    assert mapping == {"a1": "Cash"}
    # Legacy UI multiselect removed: verify label formatting logic directly
    options = list(mapping.keys())
    labels = [f"{code} – {mapping[code]}" for code in options]
    assert options == ["a1"]
    assert labels == ["a1 – Cash"]
