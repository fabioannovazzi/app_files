from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.check_entries.summary import summarize_results


def test_summarize_results_golden_path_eng():
    # Arrange: minimal mixed dataset with three mismatch types, one ok, one verified, one no_pdf
    rows = [
        {
            "movement_number": "M1",
            "check_status": "mismatch",
            "mismatch_type": "amount_mismatch",
            "explanation": "Amount mismatch: expected 100, found 80",
            # None -> defaults from mismatch_type mapping (critical)
            "severity": None,
        },
        {
            "movement_number": "M2",
            "check_status": "mismatch",
            "mismatch_type": "date_mismatch",
            "explanation": "Date mismatch: expected 2024-01-10±0 days, found 2024-01-12",
            # explicit canonical severity
            "severity": "major",
        },
        {
            "movement_number": "M3",
            "check_status": "mismatch",
            "mismatch_type": "beneficiary_mismatch",
            "explanation": (
                "Beneficiary mismatch: expected ACME (similarity ≥ 80), found Acm"
            ),
            # label case should be normalised to canonical (minor)
            "severity": "Minor",
            "beneficiary_extracted": "Acm",
        },
        {"movement_number": "M4", "check_status": "ok"},
        {"movement_number": "M5", "check_status": "verified"},
        {"movement_number": "M6", "check_status": "no_pdf"},
    ]
    df = pl.DataFrame(rows)

    # Act
    summary_text, metrics = summarize_results(None, df, "eng")

    # Assert: intro numbers
    assert (
        "The check reviewed 5 entries with PDF: 2 passed, 3 mismatches, 1 without PDF."
        in summary_text
    )

    # Assert: severity summary contains counts for each level (order-agnostic)
    assert "Overall mismatches:" in summary_text
    for part in ("1 Critical", "1 Major", "1 Minor"):
        assert part in summary_text

    # Assert: category breakdown lines
    assert "Mismatch categories" in summary_text
    assert "- 1 Critical – Amount mismatch" in summary_text
    assert "- 1 Major – Date mismatch" in summary_text
    assert "- 1 Minor – Beneficiary mismatch" in summary_text

    # Assert: beneficiary section
    assert "1 entry had beneficiary mismatches" in summary_text
    assert "- entry M3: Acm" in summary_text

    # Assert: representative examples include parsed diffs
    assert "Representative examples" in summary_text
    assert "entry M1 – Critical – Amount mismatch" in summary_text
    assert "diff 20.0" in summary_text  # 100 vs 80
    assert "entry M2 – Major – Date mismatch" in summary_text
    assert "(2 giorni)" in summary_text  # 2024-01-10 vs 2024-01-12

    # Assert: metrics tables
    expected_metrics = pl.DataFrame(
        {
            "metric": [
                "rows_with_pdf",
                "passed",
                "mismatches",
                "rows_without_pdf",
            ],
            "value": [5, 2, 3, 1],
        }
    )
    assert "metrics" in metrics
    assert_frame_equal(metrics["metrics"], expected_metrics)

    expected_breakdown = pl.DataFrame(
        {
            "mismatch_type": [
                "amount_mismatch",
                "beneficiary_mismatch",
                "date_mismatch",
            ],
            "severity": ["critical", "minor", "major"],
            "count": [1, 1, 1],
        }
    )
    actual_breakdown = metrics["mismatch_breakdown"]
    # Align dtypes for robust comparison across Polars versions
    expected_breakdown = expected_breakdown.with_columns(
        pl.col("count").cast(actual_breakdown.schema["count"])  # type: ignore[index]
    )
    assert_frame_equal(actual_breakdown, expected_breakdown)

    assert "beneficiary_mismatches" in metrics
    expected_beneficiaries = pl.DataFrame(
        {"movement_number": ["M3"], "beneficiary_extracted": ["Acm"]}
    )
    assert_frame_equal(metrics["beneficiary_mismatches"].sort("movement_number"), expected_beneficiaries)


def test_summarize_results_no_mismatches_only_intro_and_metrics():
    # Arrange: no mismatches, only ok/verified and one no_pdf
    df = pl.DataFrame(
        [
            {"movement_number": "A1", "check_status": "ok"},
            {"movement_number": "A2", "check_status": "verified"},
            {"movement_number": "A3", "check_status": "no_pdf"},
        ]
    )

    # Act
    summary_text, metrics = summarize_results(None, df, "eng")

    # Assert: exact intro, no extra sections
    expected_intro = (
        "The check reviewed 2 entries with PDF: 2 passed, 0 mismatches, 1 without PDF."
    )
    assert summary_text == expected_intro

    expected_metrics = pl.DataFrame(
        {
            "metric": [
                "rows_with_pdf",
                "passed",
                "mismatches",
                "rows_without_pdf",
            ],
            "value": [2, 2, 0, 1],
        }
    )
    assert_frame_equal(metrics["metrics"], expected_metrics)
    # No mismatch breakdown or beneficiary section expected
    assert metrics["mismatch_breakdown"].height == 0
    assert "beneficiary_mismatches" not in metrics


def test_summarize_results_unknown_severity_defaults_and_reports_message():
    # Arrange: severity value that is not recognised should default to minor and emit a message
    df = pl.DataFrame(
        [
            {
                "movement_number": "Z1",
                "check_status": "mismatch",
                "mismatch_type": "amount_mismatch",
                "explanation": "Amount mismatch: expected 10, found 9",
                "severity": "Severe",  # not a known value/label
            }
        ]
    )

    # Act
    summary_text, metrics = summarize_results(None, df, "eng")

    # Assert: mismatch accounted as Minor due to fallback
    mb = metrics["mismatch_breakdown"]
    assert mb.height == 1
    assert mb["severity"].to_list() == ["minor"]
    assert "Overall mismatches: 1 Minor" in summary_text

    # And an explanatory message is emitted
    assert "messages" in metrics
    msgs = metrics["messages"]["message"].to_list()
    assert any(
        "Unknown mismatch severity 'Severe', defaulting to minor" in m for m in msgs
    )
