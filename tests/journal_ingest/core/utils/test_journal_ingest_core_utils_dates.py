from datetime import date
import sys
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
# This test file is one level deeper than other tests under core/
ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.core.utils.dates import parse_date


def test_parse_date_valid_single_format():
    # Arrange
    value = "2023-07-15"
    formats = ("%Y-%m-%d",)

    # Act
    result = parse_date(value, formats)

    # Assert
    assert isinstance(result, date)
    assert result == date(2023, 7, 15)


def test_parse_date_tries_formats_in_order_first_match_used():
    # Arrange: ambiguous string valid for both formats
    value = "01-02-2023"
    # First treats as month-day-year -> Jan 2, 2023
    formats = ["%m-%d-%Y", "%d-%m-%Y"]

    # Act
    result = parse_date(value, formats)

    # Assert: confirms order matters (first matching format wins)
    assert result == date(2023, 1, 2)


def test_parse_date_raises_when_no_format_matches():
    # Arrange
    value = "not-a-date"
    formats = ["%Y-%m-%d", "%d/%m/%Y"]

    # Act / Assert
    with pytest.raises(ValueError) as exc:
        parse_date(value, formats)

    assert "Unable to parse date" in str(exc.value)
    assert value in str(exc.value)
