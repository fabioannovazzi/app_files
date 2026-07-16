import sys
from datetime import date
from pathlib import Path

import pytest

# Ensure local 'src' is importable for absolute imports
SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.config import LayoutConfig
from journal_ingest.strategies.text_layout import JournalStrategyTextLayout


def make_parser() -> JournalStrategyTextLayout:
    """Create a parser with minimal, permissive config.

    We rely on heuristic detail parsing (empty detail_regex) and a common
    day-first date format used by the strategy's DATE_RE.
    """

    cfg = LayoutConfig(
        drop_rules={},
        entry_header_regex="",
        detail_regex="",  # use heuristic parsing
        number_format={"decimal": ".", "thousands": ","},
        date_formats=["%d/%m/%Y"],
    )
    return JournalStrategyTextLayout(cfg)


def test_probe_positive_for_likely_layout_and_zero_for_empty():
    # Arrange
    parser = make_parser()
    text_good = (
        "01/02/2024 P1\n"
        "1 100-200 Office 100.00\n"
        "2 200-300 Office 0.00 100.00\f"  # ensure at least 2 pages overall
    )

    # Act
    score_good = parser.probe(b"", meta={"layout_text": text_good})
    score_empty = parser.probe(b"", meta={"layout_text": ""})

    # Assert
    assert 0.0 < score_good <= 1.0
    assert score_empty == 0.0


def test_parse_balanced_two_lines_returns_rows_with_expected_fields():
    # Arrange: two pages to avoid header-line stripping of non-amount lines
    parser = make_parser()
    text = (
        "01/02/2024 P1\n"
        "1 100-200 Office_Supplies 100.00\n"
        "2 200-300 Office_Supplies 0.00 100.00\f"  # second (blank) page
    )

    # Act
    rows = list(parser.parse(b"", meta={"layout_text": text}))

    # Assert
    assert len(rows) == 2
    # All rows have the parsed date, account fields, and numeric amounts
    for r in rows:
        assert r["entry_date"] == date(2024, 2, 1)
        assert r["account_code"] in {"100-200", "200-300"}
        assert isinstance(r.get("account_desc", ""), str)
        assert "memo" in r  # always present
    # Semantic amounts: one debit 100, one credit 100
    debits = [r["debit"] for r in rows]
    credits = [r["credit"] for r in rows]
    assert sum(x for x in debits if x is not None) == pytest.approx(100.0)
    assert sum(x for x in credits if x is not None) == pytest.approx(100.0)


def test_parse_ignores_headers_and_page_totals_and_carryover():
    # Arrange: two pages with a repeated header and page totals.
    parser = make_parser()
    page1 = (
        "HEADER\n"
        "01/02/2024 P1\n"
        "1 100-200 Widgets 100.00\n"
        "2 200-300 Widgets 0.00 100.00\n"
        "100.00 100.00\n"  # page total
    )
    page2 = (
        "HEADER\n"
        "100.00 100.00\n"  # carryover of previous total; must be first to be skipped
        "01/02/2024 P2\n"
        "3 300-400 More 125.00\n"
        "4 400-500 More 0.00 125.00\n"
        "125.00 125.00\n"  # page total matching the page sums
    )
    text = page1 + "\f" + page2

    # Act
    rows = list(parser.parse(b"", meta={"layout_text": text}))

    # Assert: four detail lines, no header/total rows included
    assert len(rows) == 4
    codes = {r["account_code"] for r in rows}
    assert codes == {"100-200", "200-300", "300-400", "400-500"}
    # All rows have the same date extracted from their page lines
    assert all(r["entry_date"] == date(2024, 2, 1) for r in rows)
    # Totals do not appear as entries; amounts sum to 225 both sides
    total_debit = sum(x or 0.0 for x in (r["debit"] for r in rows))
    total_credit = sum(x or 0.0 for x in (r["credit"] for r in rows))
    assert total_debit == pytest.approx(225.0)
    assert total_credit == pytest.approx(225.0)


def test_parse_raises_on_unbalanced_entries_per_date():
    # Arrange: single date, only a debit line -> unbalanced
    parser = make_parser()
    text = (
        "01/02/2024 P1\n"
        "1 100-200 Widgets 50.00\f"  # ensure 2 pages for header-frequency logic
    )

    # Act / Assert
    with pytest.raises(AssertionError, match="entry not balanced"):
        _ = list(parser.parse(b"", meta={"layout_text": text}))
