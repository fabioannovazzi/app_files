import pytest
import polars as pl
from datetime import datetime

from polars.testing import assert_frame_equal

from modules.charting.prepare_charts import (
    get_row_count,
    map_resample_rule_to_polars,
    perform_resample,
)


@pytest.mark.parametrize("rows,kind", [(0, "df"), (0, "lf"), (3, "df"), (3, "lf")])
def test_get_row_count_dataframe_and_lazyframe(rows: int, kind: str) -> None:
    # Arrange
    df = pl.DataFrame({"a": list(range(rows))})
    obj = df if kind == "df" else df.lazy()

    # Act
    count = get_row_count(obj)

    # Assert
    assert count == rows


@pytest.mark.parametrize(
    "rule,expected",
    [
        ("1ME", "1mo"),
        ("3ME", "3mo"),
        ("1w", "1w"),  # unchanged when not matching the ME pattern
    ],
)
def test_map_resample_rule_to_polars(rule: str, expected: str) -> None:
    # Act
    out = map_resample_rule_to_polars(rule)

    # Assert
    assert out == expected


@pytest.mark.parametrize(
    "agg,expected_vals",
    [
        ("sum", [3, 10]),
        ("bogus", [1.5, 10.0]),  # falls back to mean
    ],
)
def test_perform_resample_monthly_grouped_sum_and_default_mean(agg: str, expected_vals: list[float]) -> None:
    # Arrange: two dates in Jan and one in Feb for the same group
    df = pl.DataFrame(
        {
            "date": [
                datetime(2024, 1, 5),
                datetime(2024, 1, 15),
                datetime(2024, 2, 10),
            ],
            "grp": ["A", "A", "A"],
            "v": [1, 2, 10],
        }
    )
    lf = df.lazy()

    # Act
    out_lf = perform_resample(
        lf, time_col="date", group_by_cols=["grp"], value_cols=["v"], rule_str="1ME", agg=agg
    )

    # Assert: remains lazy and aggregates by monthly windows
    assert isinstance(out_lf, pl.LazyFrame)

    out = out_lf.collect().select(["grp", "date", "v"]).sort(["grp", "date"])  # deterministic order

    # With label="right" monthly bins, labels are the first day of next month
    expected = pl.DataFrame(
        {
            "grp": ["A", "A"],
            "date": [datetime(2024, 2, 1), datetime(2024, 3, 1)],
            "v": expected_vals,
        }
    ).select(["grp", "date", "v"]).sort(["grp", "date"])

    assert_frame_equal(out, expected)
