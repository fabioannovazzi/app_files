import math

import polars as pl
import pytest
from polars.testing import assert_frame_equal

import modules.add_attributes.pareto as pareto
from modules.add_attributes.pareto import (
    compute_pareto_ranking,
    compute_top_launches,
    infer_amount_column,
)
from modules.utilities.config import get_naming_params


def test_infer_amount_column_prefers_known_names_no_llm_call(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Product": ["A", "B"], "Sales": [10, 20], "Units": [1, 2]})
    lf = df.lazy()

    called = {"n": 0}

    def fake_run_step_json(*args, **kwargs):  # should not be called
        called["n"] += 1
        return [{"amount_column": "Units"}]

    monkeypatch.setattr(pareto, "run_step_json", fake_run_step_json)

    # Act
    result = infer_amount_column(None, lf)

    # Assert
    assert result == "Sales"
    assert called["n"] == 0  # LLM not consulted when Sales-like column exists


def test_infer_amount_column_uses_llm_when_no_amount_like(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Name": ["p1", "p2"], "X": [100, 200], "Y": [5, 10]})
    lf = df.lazy()

    def fake_run_step_json(*args, **kwargs):
        return [{"amount_column": "Y"}]

    monkeypatch.setattr(pareto, "run_step_json", fake_run_step_json)

    # Act
    result = infer_amount_column(None, lf)

    # Assert
    assert result == "Y"


def test_infer_amount_column_invalid_llm_response_returns_none(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Name": ["p1", "p2"], "A": [1, 2]})
    lf = df.lazy()

    def fake_run_step_json(*args, **kwargs):
        # Suggest a non-numeric column -> should be ignored
        return [{"amount_column": "Name"}]

    monkeypatch.setattr(pareto, "run_step_json", fake_run_step_json)

    # Act
    result = infer_amount_column(None, lf)

    # Assert
    assert result is None


def test_compute_pareto_ranking_basic_with_units():
    # Arrange
    naming = get_naming_params()
    price_col = naming["priceName"]
    df = pl.DataFrame(
        {
            "Product": ["A", "A", "B", "B", "C"],
            "Sales": [200, 100, 100, 50, 50],
            "Units": [5, 5, 5, 5, 2],
        }
    )

    # Act
    out = compute_pareto_ranking(df, "Product", "Sales")

    # Assert
    expected = pl.DataFrame(
        {
            "Product": ["A", "B", "C"],
            "total_amount": [300, 150, 50],
            "total_units": [10, 10, 2],
            price_col: [30.0, 15.0, 25.0],
            "cum_amount_pct": [300 / 500 * 100, 450 / 500 * 100, 100.0],
            "cum_units_pct": [10 / 22 * 100, 20 / 22 * 100, 100.0],
            "cum_price_pct": [30 / 70 * 100, 45 / 70 * 100, 100.0],
            "cum_share": [300 / 500 * 100, 450 / 500 * 100, 100.0],
        }
    )

    assert_frame_equal(out.select(expected.columns), expected, check_exact=False)
    assert out.get_column("rank").to_list() == [1, 2, 3]


def test_compute_pareto_ranking_filters_zero_and_null_amounts():
    # Arrange
    df = pl.DataFrame(
        {
            "Product": ["A", "B", "C"],
            "Sales": [0.0, None, 10.0],
        }
    )

    # Act
    out = compute_pareto_ranking(df, "Product", "Sales")

    # Assert
    assert out.height == 1
    assert out.get_column("Product").to_list() == ["C"]
    price_col = get_naming_params()["priceName"]
    assert out.select(pl.col(price_col)).to_series().is_null().all()
    assert out.get_column("cum_amount_pct").to_list() == [100.0]
    assert out.get_column("cum_share").to_list() == [100.0]
    assert "cum_units_pct" not in out.columns
    assert "cum_price_pct" not in out.columns


def test_compute_pareto_ranking_missing_column_raises():
    # Arrange
    df = pl.DataFrame({"Product": ["A"], "Sales": [10]})

    # Act / Assert
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        compute_pareto_ranking(df, "Product", "Amount")


def test_compute_pareto_ranking_group_filter_recomputes_rank_and_cum_pct():
    # Arrange
    naming = get_naming_params()
    price_col = naming["priceName"]
    df = pl.DataFrame(
        {
            "Segment": ["blush", "blush", "blush", "foundation", "foundation"],
            "Line": ["L1", "L2", "L3", "F1", "F2"],
            "Amount": [100, 200, 50, 300, 250],
            "Units": [10, 20, 5, 30, 25],
        }
    )

    # Act
    ranking_blush = compute_pareto_ranking(
        df, "Line", "Amount", group_col="Segment", groups=["blush"]
    )

    # Assert
    assert ranking_blush.get_column("Line").to_list() == ["L2", "L1", "L3"]
    assert ranking_blush.get_column("rank").to_list() == [1, 2, 3]
    total_amount = 200 + 100 + 50
    total_units = 20 + 10 + 5
    price_sum = (200 / 20) + (100 / 10) + (50 / 5)
    expected = pl.DataFrame(
        {
            "Line": ["L2", "L1", "L3"],
            "total_amount": [200, 100, 50],
            "total_units": [20, 10, 5],
            price_col: [10.0, 10.0, 10.0],
            "cum_amount_pct": [
                200 / total_amount * 100,
                300 / total_amount * 100,
                100.0,
            ],
            "cum_units_pct": [20 / total_units * 100, 30 / total_units * 100, 100.0],
            "cum_price_pct": [10 / price_sum * 100, 20 / price_sum * 100, 100.0],
            "cum_share": [200 / total_amount * 100, 300 / total_amount * 100, 100.0],
            "rank": [1, 2, 3],
        }
    )

    assert_frame_equal(
        ranking_blush.select(expected.columns), expected, check_exact=False
    )


def test_compute_top_launches_basic_order_and_values():
    # Arrange
    df = pl.DataFrame(
        {
            "Product": ["P1", "P1", "P2", "P3"],
            "Sales": [100, 200, 300, 50],
            "Date": ["2024-03-15", "2024-05-15", "2023-12-01", "2024-05-30"],
        }
    )

    # Act
    out = compute_top_launches(df, "Product", "Sales", "Date", months=3, top_n=2)

    # Assert
    assert out.height == 2
    assert out.get_column("Product").to_list() == ["P1", "P3"]
    assert out.get_column("period_amount").to_list() == [300, 50]

    # Verify avg_month_sales calculation is sensible and ordered
    avg_vals = out.get_column("avg_month_sales").to_list()
    assert avg_vals[0] > avg_vals[1]  # P1 should rank above P3
    assert math.isclose(avg_vals[1], 50.0, rel_tol=1e-6)


def test_compute_top_launches_top_n_zero_returns_empty_schema():
    # Arrange
    df = pl.DataFrame(
        {
            "Product": ["P1", "P1"],
            "Sales": [10, 20],
            "Date": ["2024-01-01", "2024-02-01"],
        }
    )

    # Act
    out = compute_top_launches(df, "Product", "Sales", "Date", months=3, top_n=0)

    # Assert
    assert out.height == 0
    # Returns a DataFrame with only the product column in schema
    assert list(out.schema.keys()) == ["Product"]


def test_compute_top_launches_missing_column_raises():
    # Arrange
    df = pl.DataFrame({"Product": ["P1"], "Sales": [10], "Date": ["2024-01-01"]})

    # Act / Assert
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        compute_top_launches(df, "Product", "Sales", "DateX")
