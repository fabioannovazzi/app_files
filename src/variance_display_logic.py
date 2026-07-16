from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import polars as pl

from modules.charting.chart_primitives import get_color_dictionary, millify_dataframe
from modules.data.common_data_utils import drop_columns_with_all_blancs
from modules.data.data_cleaning import set_order_for_output
from modules.data.waterfall_data_prep import change_variance_tags_to_units
from modules.utilities.config import get_config_params, get_naming_params
from modules.utilities.helpers import (
    add_running_total,
    drop_columns,
    get_data_sample,
    round_other_columns,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    get_schema_and_column_names,
    is_valid_lazyframe,
)
from modules.variance.variance_utils import (
    recalculate_price,
    replace_all_with_blanc_or_nan,
)

__all__ = ["prepare_result_dataset", "build_plotly_table_figure"]


def _start_index_at_one(
    df: pl.DataFrame | pl.LazyFrame, column_name: str
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with a 1-based row number column."""

    return df.with_row_index(column_name, offset=1)


def _set_colors(
    df: pl.DataFrame | pl.LazyFrame,
    columns: list[str],
    color_only_gt_one: bool,
) -> dict:
    """Return a mapping from column values to colour codes."""

    color_dict: dict[str, str] = {}
    palette = {
        0: ["#5E0778", "#9E1FC4", "#785A13", "#137850", "#02C478"],
        1: ["#9377C9", "#502C96", "#AEBEFC", "#FDCA6F", "#C9A277"],
        2: ["#915043", "#3D452D", "#452C27", "#202B45", "#4A6091"],
        3: ["#95BDC4", "#4F7278", "#C4A9B5", "#C4BD82", "#787455"],
        4: ["#5E0778", "#9E1FC4", "#785A13", "#137850", "#02C478"],
        5: ["#9377C9", "#502C96", "#AEBEFC", "#FDCA6F", "#C9A277"],
        6: ["#915043", "#3D452D", "#452C27", "#202B45", "#4A6091"],
        7: ["#95BDC4", "#4F7278", "#C4A9B5", "#C4BD82", "#787455"],
        8: ["#5E0778", "#9E1FC4", "#785A13", "#137850", "#02C478"],
        9: ["#9377C9", "#502C96", "#AEBEFC", "#FDCA6F", "#C9A277"],
        10: ["#915043", "#3D452D", "#452C27", "#202B45", "#4A6091"],
        11: ["#95BDC4", "#4F7278", "#C4A9B5", "#C4BD82", "#787455"],
        12: ["#5E0778", "#9E1FC4", "#785A13", "#137850", "#02C478"],
        13: ["#9377C9", "#502C96", "#AEBEFC", "#FDCA6F", "#C9A277"],
        14: ["#915043", "#3D452D", "#452C27", "#202B45", "#4A6091"],
        15: ["#95BDC4", "#4F7278", "#C4A9B5", "#C4BD82", "#787455"],
    }
    columns, _ = get_schema_and_column_names(df)
    if isinstance(df, pl.LazyFrame):
        df_local = df.select([pl.col(c) for c in columns if c in columns]).collect()
    else:
        # Use Polars column selection instead of brackets
        df_local = df.select([pl.col(c) for c in columns if c in columns])
    columns, _ = get_schema_and_column_names(df_local)
    for count, column in enumerate(columns):
        counts: dict[str, int] = {}
        for val in df_local[column].to_list():
            counts[val] = counts.get(val, 0) + 1
        if color_only_gt_one:
            counts = {k: v for k, v in counts.items() if v > 1}

        sorted_vals = sorted(counts, key=counts.get, reverse=True)
        for idx, val in enumerate(sorted_vals):
            if idx < len(palette[count]):
                color_dict[val] = palette[count][idx]

    return color_dict


def drop_columns_not_in_output(
    df: pl.DataFrame | pl.LazyFrame,
    *,
    as_lazy: bool = False,
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` without helper columns."""

    naming = get_naming_params()
    to_drop = [
        naming["drilldownKey"],
        naming["randomKey"],
        naming["numberOfNodes"],
        naming["uniqueValuesInCombination"],
        "index",
    ]

    lf = ensure_lazyframe(df)
    to_drop = find_columns_by_stem(lf, naming["normalizedStem"], to_drop, [])
    lf = drop_columns(lf, to_drop)

    columns, _ = get_schema_and_column_names(lf)
    not_null_any = lf.select(
        [pl.col(col).is_not_null().any().alias(col) for col in columns]
    ).collect()

    columns, _ = get_schema_and_column_names(lf)
    empty_cols = [c for c in columns if not not_null_any[c][0]]
    if empty_cols:
        lf = lf.drop(empty_cols)

    lf = lf.fill_null("")
    if as_lazy:
        return lf
    return lf.collect() if isinstance(df, pl.DataFrame) else lf


def prepare_result_dataset(
    df: pl.DataFrame | pl.LazyFrame,
    index_cols: list[str],
    param_dict: dict,
    chart_dict: dict,
    run: str,
    as_lazy: bool = False,
) -> tuple[pl.DataFrame | pl.LazyFrame, list[str], dict, dict]:
    """Return a cleaned DataFrame ready for display.

    Parameters
    ----------
    as_lazy:
        If ``True`` return a ``LazyFrame`` otherwise return a ``DataFrame``.
    """
    if is_valid_lazyframe(df):
        df = replace_all_with_blanc_or_nan(df, np.nan, as_lazy=True)
        df, param_dict = recalculate_price(df, param_dict)
        df = add_running_total(df)
        df, ordered = set_order_for_output(df, index_cols, param_dict)
        df = drop_columns_not_in_output(df, as_lazy=as_lazy)
        df, _, _ = round_other_columns(df, ordered)
        columns, _ = get_schema_and_column_names(df)
        output_index = [c for c in index_cols if c in columns]
        param_dict = get_data_sample(df, "result_" + run, False, param_dict)
        if is_valid_lazyframe(df):
            df = change_variance_tags_to_units(df, chart_dict)
    else:
        output_index = index_cols
    if as_lazy:
        df = df.lazy() if isinstance(df, pl.DataFrame) else df
    elif isinstance(df, pl.LazyFrame):
        df = df.collect()
    return df, output_index, param_dict, chart_dict


def build_plotly_table_figure(
    df: pl.DataFrame | pl.LazyFrame,
    index_cols: list[str],
    chart_dict: dict,
    param_dict: dict,
) -> tuple[go.Figure, dict]:
    """Create a Plotly table figure from ``df`` using a lazy pipeline."""

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    naming = get_naming_params()
    config = get_config_params()
    periods = config["periodsArray"]
    sep = naming["separatorString"]
    plotly_table = naming["plotlyTable"]
    variance_type = naming["varianceTypeName"]
    emoji_map = config[naming["emojiNumberDict"]]
    config_plot = config["configPlotlyDict"][plotly_table]
    color_dict = get_color_dictionary(chart_dict)
    grey = color_dict["greyColor"]
    very_light = color_dict["veryVeryLightGreyColor"]
    white = color_dict["whiteColor"]
    black = color_dict["blackColor"]
    row_num = naming["rowNumber"]
    variance_pct = naming["variancePercentChangeName"]
    running_total = naming["runningTotalName"]
    price_net = naming["pricePerUnitNetDiscountName"] + sep + periods[0]
    price_net_one = naming["pricePerUnitNetDiscountName"] + sep + periods[1]
    price_vol = naming["pricePerVolumeNetDiscountName"] + sep + periods[0]
    price_vol_one = naming["pricePerVolumeNetDiscountName"] + sep + periods[1]
    cat_weight_zero = naming["categoryWeightedDistributionName"] + sep + periods[0]
    cat_weight_one = naming["categoryWeightedDistributionName"] + sep + periods[1]
    tot_dist_zero = naming["totalDistributionPointsName"] + sep + periods[0]
    tot_dist_one = naming["totalDistributionPointsName"] + sep + periods[1]
    check_zero = naming["checkoutsName"] + sep + periods[0]
    check_one = naming["checkoutsName"] + sep + periods[1]
    visit_zero = naming["visitsName"] + sep + periods[0]
    visit_one = naming["visitsName"] + sep + periods[1]
    cost_zero = naming["costPerUnitName"] + sep + periods[0]
    cost_one = naming["costPerUnitName"] + sep + periods[1]
    cogs_zero = naming["cogsPerUnitName"] + sep + periods[0]
    cogs_one = naming["cogsPerUnitName"] + sep + periods[1]
    cogs_vol_zero = naming["cogsPerVolumeName"] + sep + periods[0]
    cogs_vol_one = naming["cogsPerVolumeName"] + sep + periods[1]
    indirect_zero = naming["indirectCostsName"] + sep + periods[0]
    indirect_one = naming["indirectCostsName"] + sep + periods[1]
    margin_zero = naming["netMarginName"] + sep + periods[0]
    margin_one = naming["netMarginName"] + sep + periods[1]
    do_not_show = [
        running_total,
        variance_pct,
        price_net,
        price_net_one,
        price_vol,
        price_vol_one,
        cat_weight_zero,
        cat_weight_one,
        tot_dist_zero,
        tot_dist_one,
        check_zero,
        check_one,
        visit_zero,
        visit_one,
        cost_zero,
        cost_one,
        cogs_zero,
        cogs_one,
        cogs_vol_zero,
        cogs_vol_one,
        indirect_zero,
        indirect_one,
        margin_zero,
        margin_one,
    ]
    index_with_var = index_cols + [variance_type]
    columns, _ = get_schema_and_column_names(lf)
    to_drop = [c for c in columns if c not in index_cols]
    lf = drop_columns(lf, to_drop)
    lf = _start_index_at_one(lf, row_num)
    lf = lf.with_columns(
        pl.col(row_num).map_elements(
            lambda x: emoji_map.get(x, x), return_dtype=pl.Utf8
        )
    )
    columns, _ = get_schema_and_column_names(lf)
    for col in columns:
        if col != row_num and col not in index_with_var:
            lf, _ = millify_dataframe(lf, col, None, col, chart_dict)
    bold_cols = {c: f"<b>{c}</b>" for c in columns}
    lf = lf.rename(bold_cols)
    df = lf.collect()
    colors = _set_colors(df, index_cols, True)
    columns, _ = get_schema_and_column_names(df)
    number_rows = df.height
    color_array = []
    for col in columns:
        if col in index_with_var:
            array = df[col].to_list()
            row_colors = [colors.get(x, grey) if x is not None else grey for x in array]
        else:
            row_colors = [grey] * number_rows
        color_array.append(row_colors)
    format_array: list[str] = []
    align_array: list[str] = []
    width_array: list[int] = []
    for col in columns:
        if col == row_num:
            format_array.append("")
            align_array.append("center")
            width_array.append(1)
        elif col not in index_with_var:
            fmt = ",.0f" if col == variance_pct else ",.3s"
            format_array.append(fmt)
            align_array.append("right")
            width_array.append(2)
        else:
            format_array.append("")
            align_array.append("left")
            width_array.append(3)
    columns, _ = get_schema_and_column_names(df)
    fig = go.Figure(
        data=[
            go.Table(
                columnwidth=width_array,
                header=dict(
                    values=list(columns),
                    align=align_array,
                    line=dict(color=very_light, width=0),
                    fill_color=white,
                    font=dict(color=black),
                    height=45,
                ),
                cells=dict(
                    values=df.transpose().to_numpy().tolist(),
                    line=dict(color=very_light, width=0),
                    fill_color=[[white, white, white, white, white] * 5],
                    align=align_array,
                    font=dict(color=color_array),
                    height=35,
                ),
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=5, r=5, b=0, t=10),
        width=len(columns) * 100,
        height=45 + number_rows * 35,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig, config_plot
