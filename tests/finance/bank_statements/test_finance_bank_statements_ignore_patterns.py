from __future__ import annotations

from src.finance.bank_statements.ignore_patterns import DROP_PATTERNS


def test_drop_balance_summary_pattern_matches() -> None:
    line = "01/12/2023    1.234,56    0    1.234,56"
    patterns = DROP_PATTERNS["drop_balance_summary"]
    assert any(pat.match(line) for pat in patterns)
