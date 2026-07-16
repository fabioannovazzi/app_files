import polars as pl
import pytest

from modules.charting.plot_charts import (
    get_uniform_text_min_size,
    plot_ecdf_charts,
    plot_histogram_charts,
)
from modules.utilities.config import get_naming_params


def test_get_uniform_text_min_size_basic_and_casts_to_int():
    # Arrange
    naming = {"uniformTextMinSize": "uts"}
    config = {"uts": "16"}  # accepts string and returns int

    # Act
    result = get_uniform_text_min_size(config, naming)

    # Assert
    assert isinstance(result, int)
    assert result == 16


def test_get_uniform_text_min_size_missing_key_raises_keyerror():
    # Arrange
    naming = {"uniformTextMinSize": "uts"}
    config = {}

    # Act / Assert
    with pytest.raises(KeyError):
        get_uniform_text_min_size(config, naming)


def _minimal_chartdict_for_distribution(chosen_chart_value: str) -> dict:
    """Build the minimal chartDict required to enter early validation paths."""
    naming = get_naming_params()
    return {
        naming["rowToPlotName"]: "",
        naming["smallMultiplesColumn"]: None,
        naming["xAxisMetric"]: None,
        naming["chosenChart"]: chosen_chart_value,
    }


def _assert_empty_dataset_error(param_dict: dict):
    naming = get_naming_params()
    arr_key = naming["appMessageArray"]
    content_key = naming["appMessageContent"]
    type_key = naming["appMessageType"]
    error_type = naming["errorMessageType"]

    assert arr_key in param_dict and isinstance(param_dict[arr_key], list)
    assert len(param_dict[arr_key]) == 1
    msg = param_dict[arr_key][0]
    assert msg[type_key] == error_type
    assert "Empty dataset" in msg[content_key]


def test_plot_histogram_charts_adds_error_message_when_df_invalid():
    # Arrange: empty DataFrame => not a valid LazyFrame/DataFrame for plotting
    empty_df = pl.DataFrame({})
    naming = get_naming_params()
    chartdict = _minimal_chartdict_for_distribution(naming["histogramChart"])

    # Act
    out_param = plot_histogram_charts(
        empty_df, indexCols=[], valueCols=[], chartDict=chartdict, dateChoice=None, paramDict={}
    )

    # Assert
    _assert_empty_dataset_error(out_param)


def test_plot_ecdf_charts_adds_error_message_when_input_not_dataframe():
    # Arrange: a non-DataFrame/LazyFrame object forces validation error path
    bad_input = "not_a_frame"
    naming = get_naming_params()
    chartdict = _minimal_chartdict_for_distribution(naming["ecdfChart"])

    # Act
    out_param = plot_ecdf_charts(
        bad_input, indexCols=[], valueCols=[], chartDict=chartdict, dateChoice=None, paramDict={}
    )

    # Assert
    _assert_empty_dataset_error(out_param)
