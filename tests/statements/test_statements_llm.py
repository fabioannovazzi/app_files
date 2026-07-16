import sys
from pathlib import Path

import pytest

# Ensure 'src' is on sys.path so 'statements' resolves from the real package
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from statements.llm import extract_transactions_llm
from statements import llm as llm_module
from statements.schema import Transaction


def test_extract_transactions_llm_returns_empty_when_api_key_missing(monkeypatch):
    # Arrange: ensure key is absent and guard against accidental parsing work
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm_module, "parse_date", lambda *a, **k: (_ for _ in ()).throw(AssertionError("parse_date should not be called")))
    monkeypatch.setattr(llm_module, "parse_number", lambda *a, **k: (_ for _ in ()).throw(AssertionError("parse_number should not be called")))

    # Act
    result = extract_transactions_llm("some block text", "en")

    # Assert
    assert result == []


def test_extract_transactions_llm_treats_empty_api_key_as_missing(monkeypatch):
    # Arrange
    monkeypatch.setenv("LLM_API_KEY", "")  # empty string should be treated as missing

    # Act
    result = extract_transactions_llm("irrelevant", "en")

    # Assert
    assert result == []


def test_extract_transactions_llm_with_api_key_returns_list_and_is_idempotent(monkeypatch):
    # Arrange
    monkeypatch.setenv("LLM_API_KEY", "dummy-token")

    # Act
    r1 = extract_transactions_llm("Payment 10 €", "en")
    r2 = extract_transactions_llm("Payment 10 €", "en")

    # Assert: returns a list of Transaction objects (possibly empty) and is stable
    assert isinstance(r1, list)
    assert r1 == r2
    assert all(isinstance(tx, Transaction) for tx in r1)
