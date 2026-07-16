from __future__ import annotations

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_primitives import (
    get_color_dictionary,
    get_hightlight_color,
)
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_schema_and_column_names

__all__ = ["plot_upset"]

_ACTIVE_COLOR = "#2F2F2F"
_INACTIVE_COLOR = "#D8D2CA"
_ROW_FILL_COLOR = "#F7F5F1"
_AXIS_COLOR = "#2B2B2B"
_FONT_SIZE = 12


def plot_upset(df: pl.DataFrame | pl.LazyFrame, chart_dict: dict) -> go.Figure:
    """Return an UpSet chart with intersection bars and membership matrix."""
    naming = get_naming_params()
    min_key = naming["minIntersectionSize"]
    highlight_key = naming["highlightedDimension"]

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    columns, schema = get_schema_and_column_names(lf)
    bool_cols = [c for c in columns if schema[c] == pl.Boolean]
    if not bool_cols:
        return go.Figure()

    sets_expr = [pl.when(pl.col(c)).then(pl.lit(c)).otherwise(None) for c in bool_cols]
    counts = (
        lf.with_columns(pl.concat_list(sets_expr).list.drop_nulls().alias("_sets"))
        .filter(pl.col("_sets").list.len() > 0)
        .with_columns(pl.col("_sets").list.sort())
        .with_columns(pl.col("_sets").list.sort().list.join("&"))
        .group_by("_sets")
        .len()
        .rename({"len": "count"})
        .filter(pl.col("count") >= chart_dict.get(min_key, 1))
        .sort("count", descending=True)
        .collect()
    )
    if counts.is_empty():
        return go.Figure()

    color_dict = get_color_dictionary(chart_dict)
    highlight_color = get_hightlight_color(chart_dict, color_dict)
    highlight_sets = set(chart_dict.get(highlight_key, []))
    colors: list[str] = []
    labels = counts["_sets"].to_list()
    memberships = [set(label.split("&")) for label in labels]
    for membership in memberships:
        if highlight_sets and highlight_sets.issubset(membership):
            colors.append(highlight_color)
        else:
            colors.append(_ACTIVE_COLOR)

    x_positions = list(range(len(labels)))
    count_values = counts["count"].to_list()
    set_labels = list(reversed(bool_cols))
    set_positions = {name: index for index, name in enumerate(set_labels)}
    set_total_row = (
        lf.select([pl.col(c).sum().alias(c) for c in bool_cols]).collect().to_dicts()[0]
    )
    set_sizes = [int(set_total_row.get(name) or 0) for name in set_labels]
    x_range = [-0.55, max(len(labels) - 0.45, 0.55)]
    set_size_limit = max(set_sizes) * 1.32 if set_sizes else 1
    set_size_range = [set_size_limit, 0]
    matrix_y_range = [-0.5, len(set_labels) - 0.5]
    chart_width = min(max(560 + len(labels) * 42, 680), 1100)
    chart_height = min(max(340 + len(set_labels) * 44, 440), 720)

    fig = make_subplots(
        rows=2,
        cols=3,
        column_widths=[0.22, 0.12, 0.66],
        row_heights=[0.68, 0.32],
        horizontal_spacing=0.01,
        vertical_spacing=0.015,
        specs=[
            [{"type": "xy"}, {"type": "xy"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}, {"type": "xy"}],
        ],
    )
    fig.add_trace(
        go.Bar(
            name="Intersection size",
            x=x_positions,
            y=count_values,
            width=0.32,
            marker_color=colors,
            marker_line_width=0,
            text=[str(value) for value in count_values],
            textposition="outside",
            textfont={"color": _AXIS_COLOR, "size": _FONT_SIZE},
            cliponaxis=False,
            hovertemplate=("%{customdata}<br>Intersection size: %{y}<extra></extra>"),
            customdata=labels,
        ),
        row=1,
        col=3,
    )
    fig.add_trace(
        go.Bar(
            name="Set size",
            x=set_sizes,
            y=list(range(len(set_labels))),
            orientation="h",
            width=0.34,
            base=0,
            marker_color=_ACTIVE_COLOR,
            marker_line_width=0,
            text=[str(value) for value in set_sizes],
            textposition="outside",
            textfont={"color": _AXIS_COLOR, "size": _FONT_SIZE},
            cliponaxis=False,
            hovertemplate="Set: %{customdata}<br>Set size: %{x}<extra></extra>",
            customdata=set_labels,
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            name="Set labels",
            x=[1] * len(set_labels),
            y=list(range(len(set_labels))),
            mode="text",
            text=set_labels,
            textposition="middle left",
            textfont={"color": _AXIS_COLOR, "size": _FONT_SIZE},
            cliponaxis=False,
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=2,
    )

    inactive_x: list[int] = []
    inactive_y: list[int] = []
    active_x: list[int] = []
    active_y: list[int] = []
    active_colors: list[str] = []
    for x_value, membership, color in zip(x_positions, memberships, colors):
        active_rows = [set_positions[item] for item in set_labels if item in membership]
        for set_name in set_labels:
            y_value = set_positions[set_name]
            if set_name in membership:
                active_x.append(x_value)
                active_y.append(y_value)
                active_colors.append(color)
            else:
                inactive_x.append(x_value)
                inactive_y.append(y_value)
        if len(active_rows) >= 2:
            fig.add_trace(
                go.Scatter(
                    name="Membership connector",
                    x=[x_value, x_value],
                    y=[min(active_rows), max(active_rows)],
                    mode="lines",
                    line={"color": color, "width": 2.4},
                    hoverinfo="skip",
                    showlegend=False,
                ),
                row=2,
                col=3,
            )

    fig.add_trace(
        go.Scatter(
            name="Not in intersection",
            x=inactive_x,
            y=inactive_y,
            mode="markers",
            marker={"color": _INACTIVE_COLOR, "size": 8},
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=3,
    )
    fig.add_trace(
        go.Scatter(
            name="In intersection",
            x=active_x,
            y=active_y,
            mode="markers",
            marker={
                "color": active_colors,
                "size": 10,
                "line": {"color": "white", "width": 0.6},
            },
            hovertemplate="Set: %{customdata}<extra></extra>",
            customdata=[set_labels[y_value] for y_value in active_y],
            showlegend=False,
        ),
        row=2,
        col=3,
    )

    for y_value in range(len(set_labels)):
        if y_value % 2 == 0:
            fig.add_shape(
                type="rect",
                x0=x_range[0],
                x1=x_range[1],
                y0=y_value - 0.5,
                y1=y_value + 0.5,
                fillcolor=_ROW_FILL_COLOR,
                line={"width": 0},
                layer="below",
                row=2,
                col=3,
            )

    fig.update_layout(
        bargap=0.2,
        width=chart_width,
        height=chart_height,
        margin=dict(l=35, r=25, t=30, b=30),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"color": _AXIS_COLOR, "family": "Arial, sans-serif", "size": _FONT_SIZE},
        hovermode="closest",
        showlegend=False,
    )
    fig.update_xaxes(visible=False, row=1, col=1)
    fig.update_yaxes(visible=False, row=1, col=1)
    fig.update_xaxes(visible=False, row=1, col=2)
    fig.update_yaxes(visible=False, row=1, col=2)
    fig.update_xaxes(
        range=x_range,
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=1,
        col=3,
    )
    fig.update_yaxes(
        range=[0, max(count_values) * 1.18],
        title_text="Intersection size",
        title_font={"color": _AXIS_COLOR, "size": _FONT_SIZE},
        showgrid=False,
        showline=True,
        linecolor=_AXIS_COLOR,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=1,
        col=3,
    )
    fig.update_xaxes(
        range=set_size_range,
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=2,
        col=1,
    )
    fig.update_yaxes(
        range=matrix_y_range,
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=2,
        col=1,
    )
    fig.update_xaxes(
        range=[0, 1],
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=2,
        col=2,
    )
    fig.update_yaxes(
        range=matrix_y_range,
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=2,
        col=2,
    )
    fig.update_xaxes(
        range=x_range,
        tickmode="array",
        tickvals=x_positions,
        ticktext=["" for _ in labels],
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
        row=2,
        col=3,
    )
    fig.update_yaxes(
        range=matrix_y_range,
        tickmode="array",
        tickvals=list(range(len(set_labels))),
        ticktext=["" for _ in set_labels],
        row=2,
        col=3,
        showgrid=False,
        showline=False,
        showticklabels=False,
        ticks="",
        zeroline=False,
    )
    return fig
