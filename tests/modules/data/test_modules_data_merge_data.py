from __future__ import annotations

import polars as pl
from polars.testing import assert_frame_equal

from modules.data.merge_data import merge_main_df_with_dimension_tables
from modules.utilities.config import get_naming_params


def _collect_sorted(df_lf: pl.LazyFrame, by: list[str]) -> pl.DataFrame:
    return df_lf.sort(by).collect()


def _get_messages(param_dict: dict, *, msg_type: str | None = None, contains: str | None = None) -> list[dict]:
    naming = get_naming_params()
    arr_key = naming["appMessageArray"]
    type_key = naming["appMessageType"]
    content_key = naming["appMessageContent"]
    msgs = param_dict.get(arr_key, [])
    if msg_type is not None:
        msgs = [m for m in msgs if m.get(type_key) == msg_type]
    if contains is not None:
        msgs = [m for m in msgs if contains in str(m.get(content_key, ""))]
    return msgs


def test_merge_happy_path_left_join_adds_columns_and_sets_flag_true():
    # Arrange
    naming = get_naming_params()
    multi_key = naming["multipleFileUploadArray"]
    is_merged_key = naming["isMergedFile"]
    info_type = naming["infoMessageType"]
    join_tab = naming["joinDatasetTab"]
    tab_key = naming["appMessageTab"]

    main_df = pl.DataFrame({"id": ["A", "B"], "value": [1, 2]})
    dim_df = pl.DataFrame({"id": ["A", "B"], "category": ["x", "y"]})
    params: dict = {multi_key: [dim_df]}

    # Act
    out_lf, out_params = merge_main_df_with_dimension_tables(params, main_df)

    # Assert
    assert isinstance(out_lf, pl.LazyFrame)
    result = _collect_sorted(out_lf, ["id"]).select(["id", "value", "category"])  # exact column order
    expected = pl.DataFrame({"id": ["A", "B"], "value": [1, 2], "category": ["x", "y"]})
    expected = expected.sort("id")
    assert_frame_equal(result, expected, check_row_order=True)

    assert out_params[is_merged_key] is True
    # An info message noting the discovered join keys is added in the join tab
    msgs = _get_messages(out_params, msg_type=info_type, contains="found these keys:")
    assert any(m.get(tab_key) == join_tab for m in msgs)


def test_merge_skips_when_dimension_has_duplicate_keys_and_keeps_original_df():
    # Arrange
    naming = get_naming_params()
    multi_key = naming["multipleFileUploadArray"]
    is_merged_key = naming["isMergedFile"]
    warn_type = naming["warningMessageType"]

    main_df = pl.DataFrame({"id": ["A", "B"], "value": [1, 2]})
    # Duplicate key "A" should trigger the dupe guard and skip the join
    dim_df = pl.DataFrame({"id": ["A", "A"], "category": ["x1", "x2"]})
    params: dict = {multi_key: [dim_df]}

    # Act
    out_lf, out_params = merge_main_df_with_dimension_tables(params, main_df)

    # Assert
    result = _collect_sorted(out_lf, ["id"]).select(["id", "value"])  # no extra columns
    expected = main_df.sort("id")
    assert_frame_equal(result, expected, check_row_order=True)

    assert out_params[is_merged_key] is False
    # Warning message explicitly mentions duplicate keys
    dup_msgs = _get_messages(out_params, msg_type=warn_type, contains="Duplicate keys detected")
    assert len(dup_msgs) >= 1


def test_merge_with_no_common_keys_adds_warning_and_leaves_df_unchanged():
    # Arrange
    naming = get_naming_params()
    multi_key = naming["multipleFileUploadArray"]
    is_merged_key = naming["isMergedFile"]
    warn_type = naming["warningMessageType"]

    main_df = pl.DataFrame({"id": ["A"], "value": [1]})
    # No overlapping column names with main_df
    dim_df = pl.DataFrame({"other_id": ["A"], "dimval": ["z"]})
    params: dict = {multi_key: [dim_df]}

    # Act
    out_lf, out_params = merge_main_df_with_dimension_tables(params, main_df)

    # Assert
    result = out_lf.collect().select(["id", "value"])  # unchanged schema
    assert_frame_equal(result, main_df, check_row_order=True)

    assert out_params[is_merged_key] is False
    # Warning message that join could not be performed
    warn_msgs = _get_messages(out_params, msg_type=warn_type, contains="Unable to join")
    assert len(warn_msgs) >= 1
