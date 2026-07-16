from __future__ import annotations

import polars as pl
import pytest

from modules.data.identify_columns import (
    build_initial_index_array,
    monetary_col_found,
    volume_col_found,
)
from modules.utilities.config import get_naming_params


class DummyUI:
    """Minimal UI stub capturing messages passed for display."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str | None]] | None = None

    def show_messages(self, messages: list[tuple[str, str, str | None]]) -> None:
        self.messages = list(messages)


def test_build_initial_index_array_casts_index_and_drops_stem_columns():
    # Arrange
    naming = get_naming_params()
    period_col = naming["periodName"]  # "Period"

    df = pl.DataFrame(
        {
            "Product": ["A", "B"],  # dimension (Utf8)
            period_col: ["P0", "P0"],  # period treated as index
            "Sales": [100.0, 200.0],  # metric (value col)
            "Units": [10, 20],  # metric (value col)
            "Unit Price": [10.0, 10.0],  # should be dropped by stem ("Price")
            "Code": [1, 2],  # numeric non-metric dimension retained as helper
        }
    )
    param = {naming["allDimensionsString"]: True}

    # Act
    out_lf, index_cols, value_cols, out_param = build_initial_index_array(df, param)

    # Assert
    assert isinstance(out_lf, pl.LazyFrame)

    out_df = out_lf.collect()
    # Dropped stem column is not present
    assert "Unit Price" not in out_df.columns
    # Index columns include string dims and the period
    assert set(index_cols) == {"Product", period_col}
    # Value columns include the known metrics
    assert set(value_cols) == {"Sales", "Units"}
    # Non-metric numeric helper columns are tracked
    assert out_param[naming["nonMetricNumericColumns"]] == ["Code"]
    # Index columns are cast to Utf8
    schema = dict(out_df.schema)
    assert schema["Product"] == pl.Utf8 and schema[period_col] == pl.Utf8


def test_build_initial_index_array_missing_required_flag_raises_keyerror():
    # Arrange
    df = pl.DataFrame({"Col": [1, 2]})
    # Act / Assert
    with pytest.raises(KeyError):
        build_initial_index_array(df, {})


def test_monetary_col_found_uses_ui_and_forwards_messages():
    # Arrange
    naming = get_naming_params()
    found_key = naming["monetaryLocalCurrencyColFound"]
    likely_key = naming["likelyLocalCurrencyValueCols"]
    param = {found_key: True, likely_key: ["total_sales"]}
    ui = DummyUI()

    # Act
    ret_params, messages = monetary_col_found(param, ui=ui)

    # Assert
    assert ret_params is param
    assert ui.messages == messages
    assert messages and messages[0][0] == "success"
    assert "total_sales" in messages[0][1]


def test_volume_col_found_uses_ui_and_forwards_messages():
    # Arrange
    naming = get_naming_params()
    found_key = naming["volumeColFound"]
    likely_key = naming["likelyVolumeCols"]
    param = {found_key: True, likely_key: ["Volume"]}
    ui = DummyUI()

    # Act
    ret_params, messages = volume_col_found(param, ui=ui)

    # Assert
    assert ret_params is param
    assert ui.messages == messages
    assert messages and messages[0][0] == "success"
    assert "Volume" in messages[0][1]
