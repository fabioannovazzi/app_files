from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.agent.config_generator import (
    LayoutConfigProposal,
    ValidatedConfig,
    gate_config,
    propose_layout_config,
)


def test_propose_layout_config_returns_valid_patterns_and_number_format():
    # Arrange: sample lines include different amount styles to drive inference
    sample_lines = [
        "1 100-200 Sales Goods sold 1,234.56 0.00",
        "2 300/400 Rent Monthly rent -1.234,56 0",
    ]

    # Act
    proposal = propose_layout_config(sample_lines)

    # Assert: proposal shape and regex groups
    assert isinstance(proposal, LayoutConfigProposal)
    entry_pat = re.compile(proposal.entry_header_regex)
    detail_pat = re.compile(proposal.detail_regex)
    assert {"entry_date", "entry_label", "unit", "location"} <= set(
        entry_pat.groupindex
    )
    assert {"line_no", "account_code", "account_desc", "memo"} <= set(
        detail_pat.groupindex
    )
    # Shapes exist and match typical tokens
    assert set(proposal.shapes.keys()) == {"date_token", "account_code", "amount"}
    assert re.compile(proposal.shapes["date_token"]).search("2024-08-27")
    assert re.compile(proposal.shapes["account_code"]).fullmatch("100-200")
    assert re.compile(proposal.shapes["amount"]).fullmatch("-1,234.56")

    # Number format candidates inferred from the mixed samples
    nf = proposal.number_format
    assert set(nf.keys()) == {"infer", "decimal_candidates", "thousands_candidates"}
    assert nf["infer"] is False
    assert set(nf["decimal_candidates"]) == {",", "."}
    assert set(nf["thousands_candidates"]) == {",", "."}

    # Date formats and drop rules are populated
    assert proposal.date_formats == ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"]
    assert proposal.drop_rules == {
        "drop_repeated_headers": True,
        "drop_page_totals_by_sum": True,
        "drop_carry_forward_by_repeat": True,
    }


def test_gate_config_accepts_valid_proposal_with_exact_threshold_match_rate():
    # Arrange: exactly 3/5 lines match the detail pattern (60%)
    sample_lines = [
        "1 100-200 Sales Memo AAA 12.00 0.00",  # match
        "2 300/400 Rent Memo BBB -5,10 0",      # match
        "3 500 Supplies Paper",                  # match (no amounts)
        "Random text line",                     # non-match
        "X 700 Wrong start 123",                # non-match
    ]
    proposal = propose_layout_config(sample_lines)

    # Act
    validated = gate_config(proposal, sample_lines)

    # Assert
    assert isinstance(validated, ValidatedConfig)
    assert validated.detail_regex == proposal.detail_regex
    # Compiled patterns are usable
    assert validated.detail_pattern.search(sample_lines[0])
    assert validated.detail_pattern.search(sample_lines[1])
    assert validated.detail_pattern.search(sample_lines[2])


def test_gate_config_raises_for_missing_required_header_groups():
    # Arrange: build a proposal whose entry regex lacks required groups
    base = propose_layout_config([])
    bad_entry_header = r"^(?P<entry_date>\d{4}-\d{2}-\d{2})\s+(?P<entry_label>.*)$"  # missing unit, location
    proposal = LayoutConfigProposal(
        entry_header_regex=bad_entry_header,
        detail_regex=base.detail_regex,
        shapes=base.shapes,
        number_format={"infer": True, "decimal_candidates": [], "thousands_candidates": []},
        date_formats=base.date_formats,
        drop_rules=base.drop_rules,
    )

    # Act / Assert
    with pytest.raises(ValueError) as exc:
        gate_config(proposal, ["1 100-200 Sales Memo 10.00 0.00"])  # sample not used before the check
    assert "Missing groups in entry_header_regex" in str(exc.value)
