from __future__ import annotations

import copy

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.utilities.config import get_naming_params
from modules.variance.variance_display import (
    clean_downloaded_df,
    process_move_rows_report_logic,
)


@pytest.mark.parametrize("as_lazy", [False, True])
def test_clean_downloaded_df_drops_helper_columns_and_preserves_data(as_lazy: bool) -> None:
    # Arrange
    naming = get_naming_params()
    drop_cols = [
        "index",
        naming["drilldownKey"],
        naming["randomKey"],
        naming["normalizedPercentName"],
        naming["normalizedAmountName"],
        naming["normalizeNumberOfNodesName"],
        naming["normalizedUniqueValuesInCombination"],
        naming["aggregatedNormalizedValue"],
    ]
    # Build a small deterministic frame with helper columns and one kept column
    data = {c: [c] for c in drop_cols}
    data["kept"] = ["ok"]
    df = pl.DataFrame(data)

    # Act
    cleaned = clean_downloaded_df(df, as_lazy=as_lazy)

    # Assert
    if as_lazy:
        assert isinstance(cleaned, pl.LazyFrame)
        cleaned_df = cleaned.collect()
    else:
        assert isinstance(cleaned, pl.DataFrame)
        cleaned_df = cleaned

    assert cleaned_df.columns == ["kept"]
    assert_frame_equal(cleaned_df, pl.DataFrame({"kept": ["ok"]}))

    # Idempotence: running again should not change the result
    cleaned_again = clean_downloaded_df(cleaned_df if not as_lazy else cleaned, as_lazy=as_lazy)
    cleaned_again_df = cleaned_again.collect() if isinstance(cleaned_again, pl.LazyFrame) else cleaned_again
    assert_frame_equal(cleaned_again_df, cleaned_df)


def test_clean_downloaded_df_raises_when_naming_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: patch naming params to miss a required key to validate strict access
    from modules import variance as _unused  # Ensure package is importable
    import modules.variance.variance_display as mod

    def _bad_naming():
        return {"drilldownKey": "drilldownKey"}  # missing "randomKey" and others

    monkeypatch.setattr(mod, "get_naming_params", _bad_naming)
    df = pl.DataFrame({"kept": [1]})

    # Act / Assert
    with pytest.raises(KeyError):
        clean_downloaded_df(df)


@pytest.mark.parametrize("as_lazy", [False, True])
def test_process_move_rows_report_logic_empty_input_types_and_param_copy(as_lazy: bool) -> None:
    # Arrange: minimal inputs trigger empty branch in process_move_rows_report
    df = pl.DataFrame({"x": [1]})
    index_cols = ["idx_a", "idx_b"]
    param_in: dict = {}
    chart_in: dict = {"color": "blue"}
    param_in_snapshot = copy.deepcopy(param_in)

    # Act
    df_list, df_details, param_out, chart_out = process_move_rows_report_logic(
        df, index_cols, param_in, chart_in, as_lazy=as_lazy
    )

    # Assert: output list/details are empty; type of list follows as_lazy
    if as_lazy:
        assert isinstance(df_list, pl.LazyFrame)
        assert df_list.collect().height == 0
    else:
        assert isinstance(df_list, pl.DataFrame)
        assert df_list.height == 0
    assert isinstance(df_details, pl.LazyFrame)
    assert df_details.collect().height == 0

    # Param dict is deep-copied, equal value but different identity
    assert param_out == param_in_snapshot
    assert param_out is not param_in

    # Chart dict is preserved in content
    assert chart_out == chart_in
