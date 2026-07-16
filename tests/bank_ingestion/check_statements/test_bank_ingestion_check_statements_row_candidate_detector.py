from __future__ import annotations

import pytest

from src.bank_ingestion.check_statements.row_candidate_detector import (
    RowCandidateDetector,
)


def make_line(text: str, x0: float, x1: float, y0: float, y1: float) -> dict:
    return {"text": text, "x0": x0, "x1": x1, "y0": y0, "y1": y1}


def test_detect_golden_path_single_candidate():
    # Arrange
    det = RowCandidateDetector()
    page_height = 1000.0
    line = make_line(
        text="2024-03-12 Grocery purchase 123.45",
        x0=50.0,
        x1=500.0,
        y0=120.0,
        y1=140.0,
    )

    # Act
    res = det.detect([line], page_index=0, page_height=page_height, lang="en")

    # Assert
    assert len(res) == 1
    cand = res[0]
    assert cand.page_index == 0
    assert cand.y_top == pytest.approx(120.0)
    assert cand.y_bottom == pytest.approx(140.0)
    assert cand.x_spans == [(50.0, 500.0)]
    assert cand.raw_text == line["text"]
    assert cand.lang == "en"
    # Feature flags reflect detected signals
    assert cand.features["has_date"] == 1.0
    assert cand.features["has_amount"] == 1.0
    assert cand.features["aligned"] == 1.0
    assert cand.features["lexical_hint"] == 0.0  # no hint words used
    # No negative flags and expected score
    assert cand.reason_flags == []
    assert cand.score == pytest.approx(0.7)


def test_detect_header_footer_penalty_boundary():
    # Arrange: boundary at 7% of height = 70.0
    det = RowCandidateDetector()
    page_height = 1000.0
    base_text = "2024-03-12 Item 123.45"
    at_boundary = make_line(base_text, 10.0, 300.0, 70.0, 90.0)
    inside_band = make_line(base_text, 10.0, 300.0, 69.0, 89.0)

    # Act
    res = det.detect([at_boundary, inside_band], page_index=3, page_height=page_height)

    # Assert
    assert len(res) == 2
    cand_boundary, cand_inside = res
    # Exactly at boundary: no footer/header penalty
    assert cand_boundary.score == pytest.approx(0.7)
    assert "footer_band" not in cand_boundary.reason_flags
    # Just inside band: penalty applied
    assert cand_inside.score == pytest.approx(0.5)
    assert "footer_band" in cand_inside.reason_flags


def test_detect_filters_total_or_balance_only_no_candidate():
    # Arrange: starts with a total/balance keyword -> filtered
    det = RowCandidateDetector()
    page_height = 1000.0
    line = make_line("Total fees 123.45", 30.0, 400.0, 200.0, 220.0)

    # Act
    res = det.detect([line], page_index=1, page_height=page_height)

    # Assert
    assert res == []
