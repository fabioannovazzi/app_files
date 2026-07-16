import sys
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.core.validate import (
    normalize_number,
    validate_entry_balances,
    validate_page_totals,
)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("1,234.56", 1234.56),  # US style
        ("1.234,56", 1234.56),  # EU style
        ("  1,234.50\u00A0", 1234.5),  # trims and removes NBSP
    ],
)
def test_normalize_number_infers_decimal_and_thousands(token: str, expected: float) -> None:
    # Act
    value = normalize_number(token)

    # Assert
    assert value == pytest.approx(expected)


def test_normalize_number_respects_explicit_format_when_infer_disabled() -> None:
    # Arrange
    token = "1.234,56"
    fmt = {"infer": False, "decimal_candidates": [","], "thousands_candidates": ["."]}

    # Act
    value = normalize_number(token, fmt)

    # Assert
    assert value == pytest.approx(1234.56)


def test_normalize_number_invalid_token_raises_value_error() -> None:
    with pytest.raises(ValueError):
        normalize_number("not_a_number")


def test_validate_entry_balances_balanced_returns_empty() -> None:
    # Arrange
    rows = [
        {
            "entry_date": "2025-01-01",
            "entry_label": "A",
            "unit": "USD",
            "location": "HQ",
            "debit": 100.0,
            "credit": 0.0,
        },
        {
            "entry_date": "2025-01-01",
            "entry_label": "A",
            "unit": "USD",
            "location": "HQ",
            "debit": 0.0,
            "credit": 100.0,
        },
        # Nulls are treated as zeros
        {
            "entry_date": "2025-01-02",
            "entry_label": "B",
            "unit": "USD",
            "location": "HQ",
            "debit": None,
            "credit": 50.0,
        },
        {
            "entry_date": "2025-01-02",
            "entry_label": "B",
            "unit": "USD",
            "location": "HQ",
            "debit": 50.0,
            "credit": None,
        },
    ]

    # Act
    issues = validate_entry_balances(rows)

    # Assert
    assert issues == []


def test_validate_entry_balances_imbalanced_reports_issue() -> None:
    # Arrange
    rows = [
        {
            "entry_date": "2025-02-01",
            "entry_label": "C",
            "unit": "EUR",
            "location": "BR",
            "debit": 100.0,
            "credit": 0.0,
        },
        {
            "entry_date": "2025-02-01",
            "entry_label": "C",
            "unit": "EUR",
            "location": "BR",
            "debit": 0.0,
            "credit": 99.98,
        },
    ]

    # Act
    issues = validate_entry_balances(rows)

    # Assert
    assert len(issues) == 1
    assert issues[0] == ("2025-02-01", "C", "EUR", "BR", 100.0, 99.98)


def test_validate_entry_balances_empty_input_returns_empty() -> None:
    assert validate_entry_balances([]) == []


def test_validate_page_totals_matching_hints_return_no_issues() -> None:
    # Arrange
    rows = [
        {"src_page": 1, "debit": 100.0, "credit": 0.0},
        {"src_page": 1, "debit": 0.0, "credit": 50.0},
        {"src_page": 2, "debit": 25.0, "credit": 25.0},
    ]
    hints = [
        {"src_page": 1, "debit": 100.0, "credit": 50.0},
        {"src_page": 2, "debit": 25.0, "credit": 25.0},
    ]

    # Act
    issues = validate_page_totals(rows, hints)

    # Assert
    assert issues == []


def test_validate_page_totals_within_epsilon_not_flagged() -> None:
    # Arrange
    rows = [
        {"src_page": 1, "debit": 100.0, "credit": 50.0},
    ]
    # Exact epsilon difference on credit should not flag
    hints = [{"src_page": 1, "debit": 100.0, "credit": 50.01}]

    # Act
    issues = validate_page_totals(rows, hints)

    # Assert
    assert issues == []


def test_validate_page_totals_mismatch_and_ignores_unknown_pages() -> None:
    # Arrange
    rows = [
        {"src_page": 10, "debit": 40.0, "credit": 10.0},
        {"src_page": 10, "debit": 5.0, "credit": 0.0},
    ]
    hints = [
        {"src_page": 10, "debit": 50.0, "credit": 10.0},  # debit mismatch
        {"src_page": 99, "debit": 1.0, "credit": 1.0},  # page not present -> ignored
    ]

    # Act
    issues = validate_page_totals(rows, hints)

    # Assert
    assert issues == [(10, 45.0, 10.0, 50.0, 10.0)]
