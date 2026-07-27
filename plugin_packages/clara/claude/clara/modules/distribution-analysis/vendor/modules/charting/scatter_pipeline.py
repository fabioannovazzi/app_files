from __future__ import annotations

import math
from typing import Sequence

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.draw_scatter import add_scatter_traces
from modules.utilities.config import get_naming_params

__all__ = ["build_pipeline_scatter"]


_SCATTER_COLORS: Sequence[str] = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
)


def _plot_group_trace(
    fig: go.Figure,
    frame: pl.DataFrame,
    *,
    x_column: str,
    y_column: str,
    group_label: str,
    color: str,
    row: int,
    col: int,
) -> go.Figure:
    naming = get_naming_params()
    color_name = naming["colorName"]
    x_axis_metric = naming["xAxisMetric"]
    y_axis_metric = naming["yAxisMetric"]
    chart_dict = {
        x_axis_metric: x_column,
        y_axis_metric: y_column,
    }
    trace_frame = frame.with_columns(pl.lit(color).alias(color_name))
    return add_scatter_traces(
        fig,
        trace_frame,
        chart_dict,
        {},
        group_label,
        True,
        10,
        "",
        row,
        col,
        False,
        "Group",
    )


def build_pipeline_scatter(
    df: pl.DataFrame,
    *,
    x_column: str,
    y_column: str,
    group_column: str | None = None,
    facet_column: str | None = None,
) -> go.Figure:
    """Build a scatter chart figure from prepared sales rows."""
    if df.is_empty():
        raise ValueError("No data to plot.")

    required = [x_column, y_column]
    if group_column:
        required.append(group_column)
    if facet_column:
        required.append(facet_column)

    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns for scatter chart: {', '.join(missing)}"
        )

    chart_df = df.with_columns(
        pl.col(x_column).cast(pl.Float64, strict=False).alias(x_column),
        pl.col(y_column).cast(pl.Float64, strict=False).alias(y_column),
    ).drop_nulls([x_column, y_column])
    if chart_df.is_empty():
        raise ValueError("No data to plot.")

    group_key = group_column or "__scatter_group"
    if group_column:
        chart_df = chart_df.with_columns(
            pl.col(group_column).cast(pl.Utf8).fill_null("N/A").alias(group_key)
        )
    else:
        chart_df = chart_df.with_columns(pl.lit("All").alias(group_key))

    if not facet_column:
        fig: go.Figure = go.Figure()
        group_values = chart_df.get_column(group_key).unique().sort().to_list()
        for index, group_value in enumerate(group_values):
            group_df = chart_df.filter(pl.col(group_key) == group_value)
            fig = _plot_group_trace(
                fig,
                group_df,
                x_column=x_column,
                y_column=y_column,
                group_label=str(group_value),
                color=_SCATTER_COLORS[index % len(_SCATTER_COLORS)],
                row=1,
                col=1,
            )
    else:
        facet_values = chart_df.get_column(facet_column).unique().sort().to_list()
        if not facet_values:
            raise ValueError("No data to plot.")
        panel_count = len(facet_values)
        panel_cols = 2 if panel_count > 1 else 1
        panel_rows = max(1, int(math.ceil(panel_count / panel_cols)))
        fig = make_subplots(
            rows=panel_rows,
            cols=panel_cols,
            subplot_titles=[str(value) for value in facet_values],
            shared_xaxes=True,
            shared_yaxes=True,
            horizontal_spacing=0.10,
            vertical_spacing=0.16,
        )
        for panel_index, facet_value in enumerate(facet_values):
            row_index = (panel_index // panel_cols) + 1
            col_index = (panel_index % panel_cols) + 1
            facet_df = chart_df.filter(pl.col(facet_column) == facet_value)
            group_values = facet_df.get_column(group_key).unique().sort().to_list()
            for index, group_value in enumerate(group_values):
                group_df = facet_df.filter(pl.col(group_key) == group_value)
                fig = _plot_group_trace(
                    fig,
                    group_df,
                    x_column=x_column,
                    y_column=y_column,
                    group_label=str(group_value),
                    color=_SCATTER_COLORS[index % len(_SCATTER_COLORS)],
                    row=row_index,
                    col=col_index,
                )

    layout_height = 520 if not facet_column else max(520, 320 * panel_rows)
    fig.update_layout(
        template="plotly_white",
        legend_title_text=group_column or "Group",
        margin={"l": 60, "r": 40, "t": 110, "b": 60},
        height=layout_height,
    )
    return fig
