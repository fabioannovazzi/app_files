import logging

import plotly.graph_objects as go
import polars as pl

from modules.utilities.utils import get_schema_and_column_names

__all__ = ["plot_horizontal_bar"]


def plot_horizontal_bar(
    df: pl.DataFrame | pl.LazyFrame,
    x_col: str,
    y_col: str,
    *,
    title: str | None = None,
) -> go.Figure | None:
    """Return a sorted horizontal bar chart as a Plotly figure."""

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df

    columns, _ = get_schema_and_column_names(lf)
    if x_col not in columns or y_col not in columns:
        return

    lf = lf.sort(x_col, descending=False).with_columns(
        pl.col(x_col).round(0).cast(pl.Int64).alias(x_col)
    )
    df_pl = lf.collect(engine="streaming")

    rounded_values = df_pl[x_col].to_list()
    fig = go.Figure(
        go.Bar(
            x=rounded_values,
            y=df_pl[y_col].to_list(),
            orientation="h",
            marker_color="black",
            text=rounded_values,
            textposition="outside",
        )
    )
    fig.update_layout(
        xaxis_title=x_col,
        yaxis_title=y_col,
        title=title,
        margin=dict(l=10, r=10, t=30, b=30),
    )
    fig.update_xaxes(showticklabels=False)
    return fig
