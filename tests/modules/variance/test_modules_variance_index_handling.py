from __future__ import annotations

import pytest
import polars as pl
from polars.testing import assert_frame_equal

from modules.utilities.config import get_naming_params
from modules.variance.index_handling import (
    get_column_sum,
    drop_columns_with_lower_correlation,
    rank_high_cardinality_columns,
)


@pytest.mark.parametrize("to_lazy", [False, True])
def test_get_column_sum_df_and_lazyframe_with_nulls(to_lazy: bool) -> None:
    # Arrange
    df = pl.DataFrame({"amount": [1.0, None, 2.0, 3.0]})
    obj = df.lazy() if to_lazy else df

    # Act
    result = get_column_sum(obj, "amount")

    # Assert
    assert result == pytest.approx(6.0)


def test_get_column_sum_missing_column_raises() -> None:
    # Arrange
    df = pl.DataFrame({"value": [1, 2, 3]})

    # Act / Assert
    with pytest.raises(Exception):
        # Polars raises ColumnNotFoundError; keep assertion generic to avoid
        # version-specific exception classes.
        get_column_sum(df, "amount")


def test_drop_columns_with_lower_correlation_drops_and_groups() -> None:
    # Arrange
    naming = get_naming_params()
    period = naming["periodName"]
    dropped_key = naming["droppedLowCorrelationCols"]

    df = pl.DataFrame(
        {
            period: ["P1", "P1", "P2", "P2"],
            "A": ["x", "x", "y", "y"],
            "B": ["b1", "b2", "b3", "b4"],
            "value": [10, 20, 5, 7],
        }
    )
    index_cols = [period, "A", "B"]
    value_cols = ["value"]
    correlations = {"A": 0.8}  # only A survives; B should be dropped
    param_dict: dict = {}
    drop_cols: list[str] = []

    # Act
    out_df, out_index_cols, out_params, out_drop_cols = drop_columns_with_lower_correlation(
        df, index_cols, value_cols, correlations, param_dict, drop_cols
    )

    # Assert: column B dropped, grouped by (A, Period) and values summed
    expected = pl.DataFrame({period: ["P1", "P2"], "A": ["x", "y"], "value": [30, 12]})
    # Order-agnostic compare
    out_df_sorted = out_df.sort([period, "A"]).select([period, "A", "value"])
    expected_sorted = expected.sort([period, "A"]).select([period, "A", "value"])
    assert_frame_equal(out_df_sorted, expected_sorted)

    assert set(out_index_cols) == {period, "A"}
    assert out_drop_cols == ["B"]
    assert out_params[dropped_key] == ["B"]


def test_drop_columns_with_lower_correlation_respects_disable_flag() -> None:
    # Arrange
    naming = get_naming_params()
    period = naming["periodName"]
    dropped_key = naming["droppedLowCorrelationCols"]
    disable_key = naming["dropLowCorrelationCols"]

    df = pl.DataFrame(
        {period: ["P1", "P1"], "A": ["x", "x"], "B": ["b1", "b2"], "value": [1, 2]}
    )
    index_cols = [period, "A", "B"]
    value_cols = ["value"]
    correlations = {"A": 0.9}
    param_dict = {disable_key: False}
    drop_cols = ["Z"]  # pre-existing suggestion should be ignored

    # Act
    out_df, out_index_cols, out_params, out_drop_cols = drop_columns_with_lower_correlation(
        df, index_cols, value_cols, correlations, param_dict, drop_cols
    )

    # Assert: dataset unchanged, nothing dropped
    assert set(out_df.columns) == set(df.columns)
    assert out_index_cols == index_cols
    assert out_drop_cols == []
    assert out_params[dropped_key] == []


def test_rank_high_cardinality_marks_bottom_share_items(monkeypatch) -> None:
    # Arrange
    naming = get_naming_params()
    rank_col = naming["rankName"]
    monetary = naming["monetaryLocalCurrencyName"]
    met = naming["metConditionValue"]
    not_met = naming["notMetConditionValue"]

    data = pl.DataFrame(
        {
            "category": ["a", "b", "c", "d", "e"],
            monetary: [100, 80, 50, 10, 5],
        }
    )

    # Increase threshold so only top 3 categories are "not_met" and bottom 2 are "met".
    # We patch the function resolved inside the target module.
    from modules.variance import index_handling as ih  # local alias for monkeypatch

    real_get_config = ih.get_config_params

    def _patched_config():
        cfg = real_get_config()
        cfg[naming["aggregateLowerValueItems"]] = 0.6  # keep ranks >= 60% (top 3 of 5)
        return cfg

    monkeypatch.setattr(ih, "get_config_params", _patched_config)

    # Act
    out = rank_high_cardinality_columns(data, "category", {})

    # Assert
    assert isinstance(out, pl.DataFrame)
    marks = {row["category"]: row[rank_col] for row in out.select(["category", rank_col]).to_dicts()}
    # Bottom two (by value) should be met; top three should be not met
    assert marks == {"a": not_met, "b": not_met, "c": not_met, "d": met, "e": met}


def test_rank_high_cardinality_preserves_lazyframe(monkeypatch) -> None:
    # Arrange
    naming = get_naming_params()
    monetary = naming["monetaryLocalCurrencyName"]
    from modules.variance import index_handling as ih

    real_get_config = ih.get_config_params

    def _patched_config():
        cfg = real_get_config()
        cfg[naming["aggregateLowerValueItems"]] = 0.5
        return cfg

    monkeypatch.setattr(ih, "get_config_params", _patched_config)

    lf = pl.DataFrame({"category": ["x", "y"], monetary: [1, 2]}).lazy()

    # Act
    out = rank_high_cardinality_columns(lf, "category", {})

    # Assert
    assert isinstance(out, pl.LazyFrame)
    assert set(out.collect().columns) >= {"category", monetary, naming["rankName"]}
