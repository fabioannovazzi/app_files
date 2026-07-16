from __future__ import annotations

from typing import Sequence

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.draw_bubble import start_bubble_axes_from_zero
from modules.utilities.config import get_naming_params

__all__ = ["build_pipeline_bubble"]


def _normalize_size(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    max_value = max(values)
    if max_value <= 0:
        return [18.0 for _ in values]
    return [max(8.0, (value / max_value) * 48.0) for value in values]


def _build_bubble_trace(
    frame: pl.DataFrame,
    *,
    x_column: str,
    y_column: str,
    size_column: str,
    color_label: str,
) -> go.Scatter:
    size_values = frame.get_column(size_column).to_list()
    marker_sizes = _normalize_size([float(value) for value in size_values])
    return go.Scatter(
        x=frame.get_column(x_column).to_list(),
        y=frame.get_column(y_column).to_list(),
        mode="markers",
        name=color_label,
        marker={"size": marker_sizes, "sizemode": "diameter", "opacity": 0.75},
        customdata=size_values,
        hovertemplate=(
            f"{x_column}: %{{x:.2f}}<br>{y_column}: %{{y:.2f}}"
            f"<br>{size_column}: %{{customdata:.2f}}<extra></extra>"
        ),
    )


def build_pipeline_bubble(
    df: pl.DataFrame,
    *,
    x_column: str,
    y_column: str,
    size_column: str,
    color_column: str | None = None,
    facet_column: str | None = None,
) -> go.Figure:
    """Build a bubble chart figure from a prepared Polars frame."""
    if df.is_empty():
        raise ValueError("No data to plot.")

    required = [x_column, y_column, size_column]
    if color_column:
        required.append(color_column)
    if facet_column:
        required.append(facet_column)

    missing = [name for name in required if name not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns for bubble chart: {', '.join(missing)}"
        )

    chart_df = (
        df.with_columns(
            pl.col(x_column).cast(pl.Float64, strict=False).alias(x_column),
            pl.col(y_column).cast(pl.Float64, strict=False).alias(y_column),
            pl.col(size_column).cast(pl.Float64, strict=False).alias(size_column),
        )
        .drop_nulls([x_column, y_column, size_column])
        .filter(pl.col(size_column) > 0)
    )
    if chart_df.is_empty():
        raise ValueError("No data to plot.")

    color_key = color_column or "__bubble_color"
    if color_column:
        chart_df = chart_df.with_columns(
            pl.col(color_column).cast(pl.Utf8).fill_null("N/A").alias(color_key)
        )
    else:
        chart_df = chart_df.with_columns(pl.lit("All").alias(color_key))

    naming = get_naming_params()
    chart_dict = {
        naming["xAxisMetric"]: x_column,
        naming["yAxisMetric"]: y_column,
        naming["startAxesFromZero"]: False,
        naming["minXDimension"]: 0,
        naming["maxXDimension"]: 0,
        naming["minYDimension"]: 0,
        naming["maxYDimension"]: 0,
        naming["totalName"]: "Total",
    }

    if not facet_column:
        fig = go.Figure()
        color_values = chart_df.get_column(color_key).unique().sort().to_list()
        for color_value in color_values:
            color_df = chart_df.filter(pl.col(color_key) == color_value)
            fig.add_trace(
                _build_bubble_trace(
                    color_df,
                    x_column=x_column,
                    y_column=y_column,
                    size_column=size_column,
                    color_label=str(color_value),
                )
            )
        fig = start_bubble_axes_from_zero(fig, chart_df, "", chart_dict, 1, 1)
    else:
        facet_values = chart_df.get_column(facet_column).unique().sort().to_list()
        if not facet_values:
            raise ValueError("No data to plot.")
        panel_count = len(facet_values)
        panel_cols = 2 if panel_count > 1 else 1
        panel_rows = 2 if panel_count > 2 else 1
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
            color_values = facet_df.get_column(color_key).unique().sort().to_list()
            for color_value in color_values:
                color_df = facet_df.filter(pl.col(color_key) == color_value)
                fig.add_trace(
                    _build_bubble_trace(
                        color_df,
                        x_column=x_column,
                        y_column=y_column,
                        size_column=size_column,
                        color_label=str(color_value),
                    ),
                    row=row_index,
                    col=col_index,
                )
            fig = start_bubble_axes_from_zero(
                fig,
                facet_df,
                str(facet_value),
                chart_dict,
                row_index,
                col_index,
            )
        fig.update_layout(
            showlegend=True,
            height=900 if panel_rows > 1 else 520,
            margin={"l": 60, "r": 40, "t": 110, "b": 60},
        )

    fig.update_layout(
        template="plotly_white",
        legend_title_text=color_column or "Group",
    )
    return fig
