import sys
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.core.errors import ValidationError
from journal_ingest.core.validators import validate_double_entry


def test_validate_double_entry_balanced_multiple_groups_and_rounding() -> None:
    # Arrange: two entries, both balanced; second relies on 2-decimal rounding
    lines = [
        {"entry_date": "2024-01-01", "entry_label": "Rent", "debit": 10.0, "credit": 0.0},
        {"entry_date": "2024-01-01", "entry_label": "Rent", "debit": 0.0, "credit": 3.0},
        {"entry_date": "2024-01-01", "entry_label": "Rent", "debit": 0.0, "credit": 7.0},
        # Difference of 0.001 should round to 0.00 at 2 decimals
        {"entry_date": "2024-01-02", "entry_label": "Coffee", "debit": 1.001, "credit": 0.0},
        {"entry_date": "2024-01-02", "entry_label": "Coffee", "debit": 0.0, "credit": 1.0},
    ]

    # Act / Assert
    assert validate_double_entry(lines) is None


def test_validate_double_entry_raises_on_imbalance_with_missing_keys() -> None:
    # Arrange: missing entry_date/entry_label become key ('None', 'None')
    lines = [
        {"debit": 5.0},
        {"credit": 4.99},
    ]

    # Act / Assert
    with pytest.raises(ValidationError) as exc:
        validate_double_entry(lines)

    msg = str(exc.value)
    assert "Double-entry imbalance for" in msg
    assert "('None', 'None')" in msg  # keys default to str(None)


def test_validate_double_entry_treats_missing_amounts_as_zero() -> None:
    # Arrange: None/missing amounts are treated as 0.0 and still balance
    lines = [
        {"entry_date": None, "entry_label": None, "debit": None, "credit": 10.0},
        {"entry_date": None, "entry_label": None, "debit": 10.0},  # credit missing -> 0.0
    ]

    # Act / Assert
    assert validate_double_entry(lines) is None
