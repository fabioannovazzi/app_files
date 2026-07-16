from __future__ import annotations

import sys
from pathlib import Path

# Ensure 'src' is on sys.path so 'statements' resolves from the real package
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from statements.header_map import map_headers


def test_map_headers_basic_english_synonyms():
    # Arrange
    headers = [
        "Booking Date",
        "Value Date",
        "Description",
        "Amount",
        "Currency",
        "Debit",
        "Credit",
        "Balance",
        "Reference",
    ]

    # Act
    mapping = map_headers(headers, lang="en")

    # Assert
    assert mapping == {
        "booking_date": 0,
        "value_date": 1,
        "description": 2,
        "amount": 3,
        "currency": 4,
        "debit": 5,
        "credit": 6,
        "balance": 7,
        "reference": 8,
    }


def test_map_headers_accented_and_multilingual():
    # Arrange: mix of German and French with accents/case
    headers = [
        "WÄHRUNG",  # currency (German, accent)
        "Libellé",  # description (French, accent)
        "Date de valeur",  # value_date (French)
        "Référence",  # reference (French, accent)
    ]

    # Act
    mapping = map_headers(headers, lang="fr")

    # Assert
    assert mapping == {
        "currency": 0,
        "description": 1,
        "value_date": 2,
        "reference": 3,
    }


def test_map_headers_last_match_wins_for_same_canonical():
    # Arrange: two headers that both map to balance; the later should win
    headers = ["Saldo", "Balance"]

    # Act
    mapping = map_headers(headers, lang="it")

    # Assert
    assert mapping.get("balance") == 1


def test_map_headers_no_false_positives():
    # Arrange: substrings like "debitore" must not match canonical "debit"
    headers = ["debitore", "creditore", "unknown column"]

    # Act
    mapping = map_headers(headers, lang="en")

    # Assert
    assert mapping == {}
