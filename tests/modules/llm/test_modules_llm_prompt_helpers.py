from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.llm.prompt_helpers import (
    clean_df_for_prompt,
    extract_industry_and_company_from_dict,
    replace_currency_symbols,
)
from modules.utilities.session_context import SessionContext, use_session_context


def test_clean_df_for_prompt_drops_color_and_sorts_by_rank():
    # Arrange
    df = pl.DataFrame(
        {
            "rank": [3, 1, 2],
            "count": [30, 10, 20],
            "metricA": [300.0, 100.0, 200.0],
            "colorName": ["red", "green", "blue"],  # should be dropped
        }
    )
    chart_dict = {
        # Keys expected by the function
        "countColumn": "count",
        "metricsToPlot": ["metricA"],
    }

    # Act
    out = clean_df_for_prompt(df, chart_dict)

    # Assert
    expected = pl.DataFrame(
        {
            "rank": [1, 2, 3],
            "count": [10, 20, 30],
            "metricA": [100.0, 200.0, 300.0],
        }
    )
    assert isinstance(out, pl.DataFrame)
    assert_frame_equal(out, expected)


def test_clean_df_for_prompt_limits_rows_to_30000():
    # Arrange
    n_rows = 30005
    df = pl.DataFrame(
        {
            "rank": list(range(n_rows)),
            "count": list(range(n_rows)),
        }
    )
    chart_dict = {"countColumn": "count", "metricsToPlot": []}

    # Act
    out = clean_df_for_prompt(df, chart_dict)

    # Assert
    assert isinstance(out, pl.DataFrame)
    assert out.height == 30000
    # Ensure first/last rows match sorted head semantics
    assert out[0, "rank"] == 0
    assert out[-1, "rank"] == 29999


def test_clean_df_for_prompt_missing_rank_raises():
    # Arrange
    df = pl.DataFrame({"count": [1, 2, 3]})
    chart_dict = {"countColumn": "count", "metricsToPlot": []}

    # Act / Assert
    with pytest.raises(Exception):
        clean_df_for_prompt(df, chart_dict)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Price is $5 and €3", "Price is USD5 and EUR3"),
        ("Currencies: £, ¥, ₹", "Currencies: GBP, JPY, INR"),
        ("No currency here", "No currency here"),
    ],
)
def test_replace_currency_symbols(text, expected):
    assert replace_currency_symbols(text) == expected


def test_extract_industry_and_company_sets_session_state_and_cleans(monkeypatch):
    # Arrange
    session = SessionContext.from_state({})
    # Minimal dict with recognised keys, plus an extra one that should be returned
    input_dict = {
        "Industry": "Retail",
        "companyName": "Acme Corp",
        "questions": "What is the price? It is $5.",
        "answers": ["Answer with € sign"],
        "notes": "Budget £10",  # should be cleaned and returned
    }

    # Act
    with use_session_context(session):
        cleaned = extract_industry_and_company_from_dict(input_dict.copy())

    # Assert
    # Recognised keys are stored in session_state
    ss = session.state
    assert ss.get("Industry") == "Retail"
    assert ss.get("companyName") == "Acme Corp"
    # questions/answers cleaned via currency replacement
    assert ss.get("questions") == "What is the price? It is USD5."
    assert ss.get("answers") == ["Answer with EUR sign"]
    # Unknown keys are returned, cleaned
    assert cleaned == {"notes": "Budget GBP10"}


def test_extract_industry_and_company_empty_input_returns_empty(monkeypatch):
    # Arrange
    session = SessionContext.from_state({})

    # Act
    with use_session_context(session):
        cleaned = extract_industry_and_company_from_dict({})

    # Assert
    assert cleaned == {}
    # session_state remains empty
    assert session.state == {}
