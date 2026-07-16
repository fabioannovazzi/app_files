import copy

import numpy as np
import polars as pl

from modules.charting.chart_primitives import (
    get_color_dictionary,
    millify_dataframe,
)
from modules.charting.plot_charts import plot_vertical_waterfall_chart
from modules.data.common_data_utils import drop_columns_with_all_blancs
from modules.data.data_cleaning import set_order_for_output
from modules.data.waterfall_data_prep import change_variance_tags_to_units
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    add_running_total,
    duplicate_dataframe,
    find_columns_by_stem,
    get_data_sample,
    round_other_columns,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_schema_and_column_names,
    is_valid_lazyframe,
)
from modules.variance.variance_decomposition import process_move_rows_report
from modules.variance.variance_utils import (
    recalculate_price,
    replace_all_with_blanc_or_nan,
)
from src.variance_display_logic import prepare_result_dataset


def process_move_rows_report_logic(
    df: pl.DataFrame | pl.LazyFrame,
    index_cols: list[str],
    param_dict: dict,
    chart_dict: dict,
    as_lazy: bool = False,
) -> tuple[pl.DataFrame | pl.LazyFrame, pl.DataFrame, dict, dict]:
    """Return processed move-row report data without any UI calls."""

    naming_params = get_naming_params()
    df_list_tmp, df_details_tmp, _df_snapshot, param_copy = process_move_rows_report(
        df, index_cols, param_dict, chart_dict, naming_params["moveRowReportRunName"]
    )

    df_list, df_details, param_dict = (
        duplicate_dataframe(df_list_tmp),
        duplicate_dataframe(df_details_tmp),
        copy.deepcopy(param_copy),
    )

    df_list, _output_cols, param_dict, chart_dict = prepare_result_dataset(
        df_list,
        index_cols,
        param_dict,
        chart_dict,
        naming_params["moveRowReportRunName"],
        as_lazy,
    )

    return df_list, df_details, param_dict, chart_dict


def clean_downloaded_df(dfCopy, *, as_lazy: bool = False):
    """Return ``dfCopy`` without helper columns.

    Parameters
    ----------
    as_lazy:
        Return a :class:`~polars.LazyFrame` when ``True`` otherwise a
        :class:`~polars.DataFrame`.
    """
    naming_params = get_naming_params()
    drop_cols = [
        "index",
        naming_params["drilldownKey"],
        naming_params["randomKey"],
        naming_params["normalizedPercentName"],
        naming_params["normalizedAmountName"],
        naming_params["normalizeNumberOfNodesName"],
        naming_params["normalizedUniqueValuesInCombination"],
        naming_params["aggregatedNormalizedValue"],
    ]

    df = ensure_polars_df(dfCopy).drop(drop_cols, strict=False)

    if as_lazy:
        return ensure_lazyframe(df)

    return df
