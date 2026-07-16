from __future__ import annotations

import copy

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.utilities.config import get_naming_params
from modules.variance.variance_decomposition import (
    add_drill_down_params_to_dict,
    get_single_row_details,
    process_move_rows_report,
    process_node_combinations,
)


def test_add_drill_down_params_merges_for_known_filecode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: patch drilldown params to include extra settings for code 42
    import modules.variance.variance_decomposition as mod

    naming = get_naming_params()
    file_code_key = naming["fileCodeName"]

    def _dd_params():
        return {42: {"extra": 1, "flag": True}}

    monkeypatch.setattr(mod, "get_drilldown_params", _dd_params)

    original = {file_code_key: 42, "unchanged": "ok"}
    snapshot = copy.deepcopy(original)

    # Act
    out = add_drill_down_params_to_dict(original)

    # Assert: input unchanged; output contains merged keys
    assert original == snapshot and out is not original
    assert out["unchanged"] == "ok"
    assert out["extra"] == 1 and out["flag"] is True


def test_add_drill_down_params_returns_copy_when_filecode_missing() -> None:
    # Arrange
    param = {"a": 1}

    # Act
    out = add_drill_down_params_to_dict(param)

    # Assert: same content, new dict object
    assert out == param and out is not param


def test_get_single_row_details_treats_nan_fill_as_wildcard() -> None:
    # Arrange
    naming = get_naming_params()
    nan_fill = naming["nanFillValue"]
    random_key = naming["randomKey"]
    loop_random_key = naming["loopRandomKey"]
    drilldown_key = naming["drilldownKey"]
    variance_type = naming["varianceTypeName"]

    df = pl.DataFrame(
        {
            "Category": ["Bikes", "Bikes", "Bikes", "Accessories"],
            "Productline": [nan_fill, "R", "M", nan_fill],
            variance_type: ["Price", "Price", "Price", "Price"],
            random_key: ["row-1", "row-2", "row-3", "row-4"],
            loop_random_key: [0, 1, 2, 3],
            "value": [100.0, 60.0, 40.0, 10.0],
        }
    )

    # Act
    details = get_single_row_details(df, ["Category", "Productline"], [], count=1)[0]

    # Assert
    expected = pl.DataFrame(
        {
            "Category": ["Bikes", "Bikes"],
            "Productline": ["R", "M"],
            variance_type: ["Price", "Price"],
            random_key: ["row-2", "row-3"],
            "value": [60.0, 40.0],
            drilldown_key: ["row-1", "row-1"],
        }
    )
    assert_frame_equal(details, expected)


def test_process_move_rows_report_calls_node_combinations_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: set insertAtRowDict to a non-empty collection to trigger the branch
    naming = get_naming_params()
    insert_key = naming["insertAtRowDict"]
    param_in = {insert_key: {0: {"k": "v"}}}

    called = {"flag": False}

    def _stub(df, index_cols, param, chart, run):  # noqa: ANN001
        called["flag"] = True
        # Return small deterministic frames and a mutated param copy
        return (
            pl.DataFrame({"x": [1]}),
            pl.DataFrame({"y": [2]}),
            pl.DataFrame({"z": [3]}),
            {**param, "touched": True},
        )

    import modules.variance.variance_decomposition as mod

    monkeypatch.setattr(mod, "process_node_combinations", _stub)

    df = pl.DataFrame({"x": [0]})
    index_cols = ["idx"]

    # Act
    df_list, df_details, df_snapshot, param_out = process_move_rows_report(
        df, index_cols, param_in, chartDict={}, run="test"
    )

    # Assert: stub called; outputs are eager DataFrames with expected content
    assert called["flag"] is True
    assert isinstance(df_list, pl.DataFrame) and df_list.height == 1
    assert isinstance(df_details, pl.DataFrame) and df_details.height == 1
    assert isinstance(df_snapshot, pl.DataFrame) and df_snapshot.height == 1
    assert param_out["touched"] is True


def test_process_move_rows_report_returns_empty_when_no_insert_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: ensure heavy function wouldn't be called (raise if it is)
    import modules.variance.variance_decomposition as mod

    def _should_not_run(*_a, **_k):  # pragma: no cover - safety net
        raise AssertionError("process_node_combinations should not be called")

    monkeypatch.setattr(mod, "process_node_combinations", _should_not_run)

    df = pl.DataFrame({"x": [0]})
    index_cols: list[str] = []
    param_in: dict = {}  # missing insertAtRowDict

    # Act
    df_list, df_details, df_snapshot, param_out = process_move_rows_report(
        df, index_cols, param_in, chartDict={}, run="test"
    )

    # Assert: all outputs are empty DataFrames; param is passed through
    for frame in (df_list, df_details, df_snapshot):
        assert isinstance(frame, pl.DataFrame)
        assert frame.height == 0
        assert frame.width == 0
    assert param_out == param_in


@pytest.mark.parametrize("as_lazy", [False, True])
def test_process_node_combinations_empty_input_yields_empty_outputs(
    as_lazy: bool,
) -> None:
    # Arrange: empty input with no schema avoids the inner recalculation branch
    df_in = pl.DataFrame()
    if as_lazy:
        df_in = df_in.lazy()

    index_cols: list[str] = []
    param_in: dict = {}
    chart: dict = {}
    naming = get_naming_params()

    # Act
    df_list, df_details, df_snapshot, param_out = process_node_combinations(
        df_in, index_cols, param_in, chart, run="r"
    )

    # Assert: output container types follow input laziness and are empty
    if as_lazy:
        assert isinstance(df_list, pl.LazyFrame)
        assert isinstance(df_details, pl.LazyFrame)
        assert isinstance(df_snapshot, pl.LazyFrame)
        assert df_list.collect().height == 0
        assert df_details.collect().height == 0
        assert df_snapshot.collect().height == 0
    else:
        assert isinstance(df_list, pl.DataFrame)
        assert isinstance(df_details, pl.DataFrame)
        assert isinstance(df_snapshot, pl.DataFrame)
        assert (
            df_list.height == 0 and df_details.height == 0 and df_snapshot.height == 0
        )

    # Minimal contract on param mutations
    assert param_out[naming["runningTotalName"]] == 0
    assert param_out[naming["rowsFoundToSubtract"]] == 1
    assert (
        param_out[naming["noMoreRowsWithRandomKey"]] is naming["notMetConditionValue"]
    )
