from __future__ import annotations

import logging
import re
from typing import Literal

import plotly.graph_objects as go
import polars as pl

from modules.charting.draw_other_charts import draw_area_chart
from modules.charting.mekko_pipeline import _AUTO_MAX_KEEP_X, _auto_top_count
from modules.charting.update_layouts import update_area_chart_layout
from modules.utilities.config import get_naming_params
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_row_count,
    get_schema_and_column_names,
)

__all__ = ["build_pipeline_area"]

_LOGGER = logging.getLogger(__name__)
_AREA_LABEL_COLOR = "#111827"


def _select_top_items(
    lf: pl.LazyFrame, dimension: str, metric_column: str, *, max_keep: int
) -> list[str]:
    cols, _ = get_schema_and_column_names(lf)
    if dimension not in cols or metric_column not in cols:
        return []
    top_n = _auto_top_count(lf, dimension, metric_column, max_keep=max_keep)
    if top_n <= 0:
        top_n = int(lf.select(pl.col(dimension).n_unique()).collect().item())
    totals = (
        lf.group_by(dimension)
        .agg(pl.col(metric_column).sum().alias("__total"))
        .collect()
    )
    if totals.is_empty():
        return []
    return [
        str(val)
        for val in totals.sort("__total", descending=True)
        .select(dimension)
        .head(top_n)
        .to_series()
        .to_list()
        if val is not None and str(val).strip()
    ]


def _normalize_palette_name(palette: str | None, naming: dict[str, str]) -> str | None:
    if not palette:
        return None
    raw = str(palette).strip()
    if not raw:
        return None

    known_values = {
        naming["cirqueColorpalette"],
        naming["modernColorpalette"],
        naming["blueAndGreenColorpalette"],
        naming["khakiAndDenimColorpalette"],
        naming["poloColorpalette"],
        naming["heatingUpColorpalette"],
        naming["tableauColorpalette"],
        naming["thinkcellColorpalette"],
        naming["IBCSColorpalette"],
        naming["bainColorpalette"],
        naming["mckinseyColorpalette"],
        naming["bcgColorpalette"],
        naming["occColorpalette"],
        naming["deloitteColorpalette"],
        naming["powerbiColorpalette"],
        naming["symphonyColorpalette"],
        naming["greysColorpalette"],
        naming["bluesColorpalette"],
        naming["orangesColorpalette"],
        naming["purplesColorpalette"],
        naming["brownsColorpalette"],
    }
    if raw in known_values:
        return raw

    key = re.sub(r"[^a-z0-9]+", "", raw.lower())
    mapped = {
        "pastel": "pastel",
        "bold": "bold",
        "muted": "muted",
        "cirque": naming["cirqueColorpalette"],
        "modern": naming["modernColorpalette"],
        "bluegreen": naming["blueAndGreenColorpalette"],
        "khakidenim": naming["khakiAndDenimColorpalette"],
        "polo": naming["poloColorpalette"],
        "heatingup": naming["heatingUpColorpalette"],
        "tableau": naming["tableauColorpalette"],
        "thinkcell": naming["thinkcellColorpalette"],
        "ibcs": naming["IBCSColorpalette"],
        "bain": naming["bainColorpalette"],
        "mckinsey": naming["mckinseyColorpalette"],
        "bcg": naming["bcgColorpalette"],
        "occ": naming["occColorpalette"],
        "deloitte": naming["deloitteColorpalette"],
        "powerbi": naming["powerbiColorpalette"],
        "symphony": naming["symphonyColorpalette"],
        "greys": naming["greysColorpalette"],
        "blues": naming["bluesColorpalette"],
        "oranges": naming["orangesColorpalette"],
        "purples": naming["purplesColorpalette"],
        "browns": naming["brownsColorpalette"],
    }
    return mapped.get(key)


def _parse_rgb(color: str) -> tuple[int, int, int] | None:
    if not color:
        return None
    value = color.strip().lower()
    if value.startswith("#") and len(value) == 7:
        try:
            r = int(value[1:3], 16)
            g = int(value[3:5], 16)
            b = int(value[5:7], 16)
            return r, g, b
        except ValueError:
            return None
    if value.startswith("rgb(") or value.startswith("rgba("):
        try:
            nums = value[value.find("(") + 1 : value.find(")")].split(",")
            r = int(float(nums[0]))
            g = int(float(nums[1]))
            b = int(float(nums[2]))
            return r, g, b
        except (ValueError, IndexError):
            return None
    return None


def _format_absolute_value(value: float, value_display_divisor: float) -> str:
    number = float(value or 0.0)
    divisor = float(value_display_divisor or 1.0)
    if divisor == 0:
        divisor = 1.0
    return f"{number / divisor:.1f}"


def _add_end_labels(
    fig: go.Figure,
    df: pl.DataFrame,
    dimension: str,
    metric_column: str,
    period_column: str,
    labels: list[str],
    *,
    min_share: float = 5.0,
    value_mode: Literal["percent", "absolute"] = "percent",
) -> None:
    if df.is_empty():
        return
    last_period = df.select(pl.col(period_column).max()).item()
    df_last = (
        df.filter(pl.col(period_column) == last_period)
        .group_by(dimension)
        .agg(pl.col(metric_column).sum().alias("__value"))
    )
    if df_last.is_empty():
        return
    values = {row[0]: float(row[1]) for row in df_last.iter_rows()}
    total = sum(values.values())
    if total <= 0:
        return
    cumulative_share = 0.0
    cumulative_value = 0.0
    for idx, label in enumerate(labels):
        value = float(values.get(label, 0.0))
        if value <= 0:
            continue
        share = value / total * 100
        if share < min_share:
            cumulative_share += share
            cumulative_value += value
            continue
        y_pos = (
            cumulative_share + (share / 2)
            if value_mode == "percent"
            else cumulative_value + (value / 2)
        )
        fig.add_annotation(
            text=str(label),
            x=1.002,
            y=y_pos,
            xref="paper",
            yref="y",
            showarrow=False,
            align="left",
            xanchor="left",
            xshift=2,
            font=dict(color=_AREA_LABEL_COLOR, size=12),
        )
        cumulative_share += share
        cumulative_value += value


def _add_value_labels(
    fig: go.Figure,
    df: pl.DataFrame,
    dimension: str,
    metric_column: str,
    period_column: str,
    labels: list[str],
    *,
    min_share: float = 5.0,
    value_mode: Literal["percent", "absolute"] = "percent",
    value_display_divisor: float = 1.0,
) -> None:
    if df.is_empty():
        return
    periods = df.select(pl.col(period_column).unique().sort()).to_series().to_list()
    if not periods:
        return

    df_period = df.group_by([period_column, dimension]).agg(
        pl.col(metric_column).sum().alias("__value")
    )
    totals = df_period.group_by(period_column).agg(
        pl.col("__value").sum().alias("__total")
    )
    share_df = df_period.join(totals, on=period_column).with_columns(
        (pl.col("__value") / pl.col("__total") * 100).alias("__share")
    )
    period_share_map: dict[object, dict[str, float]] = {}
    period_value_map: dict[object, dict[str, float]] = {}
    for row in share_df.iter_rows(named=True):
        period = row[period_column]
        label = str(row[dimension])
        period_share_map.setdefault(period, {})[label] = float(row["__share"])
        period_value_map.setdefault(period, {})[label] = float(row["__value"])

    period_index = {period: idx for idx, period in enumerate(periods)}
    min_period_gap = 2
    first_period = periods[0]
    last_period = periods[-1]
    max_period_by_label: dict[str, object] = {}
    max_share_by_label: dict[str, float] = {}
    for label in labels:
        shares = [
            (period, period_share_map.get(period, {}).get(label, 0.0))
            for period in periods
        ]
        if not shares:
            continue
        max_period, max_share = max(shares, key=lambda item: item[1])
        max_period_by_label[label] = max_period
        max_share_by_label[label] = float(max_share)

    selected_by_label: dict[str, set[object]] = {label: set() for label in labels}
    if value_mode == "percent":
        first_idx = 0
        last_idx = len(periods) - 1
        for label in labels:
            first_share = period_share_map.get(first_period, {}).get(label, 0.0)
            last_share = period_share_map.get(last_period, {}).get(label, 0.0)
            if first_share >= min_share:
                selected_by_label[label].add(first_period)
            if last_share >= min_share:
                selected_by_label[label].add(last_period)

            shares = [
                (period, period_share_map.get(period, {}).get(label, 0.0))
                for period in periods
            ]
            if not shares:
                continue
            max_period, max_share = max(shares, key=lambda item: item[1])
            min_period, min_share_value = min(shares, key=lambda item: item[1])
            for candidate_period, candidate_share in (
                (max_period, max_share),
                (min_period, min_share_value),
            ):
                if candidate_share < min_share:
                    continue
                if candidate_period in selected_by_label[label]:
                    continue
                idx = period_index.get(candidate_period)
                if idx is None:
                    continue
                if (
                    abs(idx - first_idx) <= min_period_gap
                    or abs(idx - last_idx) <= min_period_gap
                ):
                    continue
                selected_by_label[label].add(candidate_period)
            if max_share >= min_share:
                selected_by_label[label].add(max_period)
    else:
        label_candidates: dict[str, list[tuple[int, object, float]]] = {}
        for label in labels:
            shares = [(p, period_share_map.get(p, {}).get(label, 0.0)) for p in periods]
            if not shares:
                continue
            values = [(p, period_value_map.get(p, {}).get(label, 0.0)) for p in periods]
            selection_points = values
            max_period, max_metric = max(selection_points, key=lambda item: item[1])
            min_period, min_metric = min(selection_points, key=lambda item: item[1])
            max_share = period_share_map.get(max_period, {}).get(label, 0.0)
            min_share_val = period_share_map.get(min_period, {}).get(label, 0.0)
            candidates: list[tuple[int, object, float]] = []
            if max_share >= min_share:
                candidates.append((2, max_period, max_metric))
            if min_share_val >= min_share:
                candidates.append((3, min_period, min_metric))
            seen = set()
            label_candidates[label] = [
                c for c in candidates if not (c[1] in seen or seen.add(c[1]))
            ]

        used_indices: list[int] = []
        for label in labels:
            first_share = period_share_map.get(first_period, {}).get(label, 0.0)
            last_share = period_share_map.get(last_period, {}).get(label, 0.0)
            if first_share >= min_share:
                selected_by_label[label].add(first_period)
                idx = period_index.get(first_period)
                if idx is not None:
                    used_indices.append(idx)
            if last_share >= min_share:
                selected_by_label[label].add(last_period)
                idx = period_index.get(last_period)
                if idx is not None:
                    used_indices.append(idx)

        candidate_list: list[tuple[int, float, int, object, str]] = []
        for label, candidates in label_candidates.items():
            for priority, period, metric_value in candidates:
                idx = period_index.get(period)
                if idx is None:
                    continue
                candidate_list.append((priority, -metric_value, idx, period, label))

        candidate_list.sort()

        for _priority, _neg_share, idx, period, label in candidate_list:
            if period in selected_by_label.get(label, set()):
                continue
            if any(abs(idx - used_idx) <= min_period_gap for used_idx in used_indices):
                continue
            selected_by_label[label].add(period)
            used_indices.append(idx)
        for label in labels:
            max_period = max_period_by_label.get(label)
            max_share = max_share_by_label.get(label, 0.0)
            if max_period is not None and max_share >= min_share:
                selected_by_label[label].add(max_period)

    series_name_min_share = max(min_share + 2.0, 7.0)
    series_name_added: set[str] = set()
    for period in periods:
        period_shares = period_share_map.get(period, {})
        period_values = period_value_map.get(period, {})
        cumulative_share = 0.0
        cumulative_value = 0.0
        for idx, label in enumerate(labels):
            share = float(period_shares.get(label, 0.0))
            value = float(period_values.get(label, 0.0))
            if share <= 0:
                continue
            if share < min_share:
                cumulative_share += share
                cumulative_value += value
                continue
            if period not in selected_by_label.get(label, set()):
                cumulative_share += share
                cumulative_value += value
                continue
            y_pos = (
                cumulative_share + (share / 2)
                if value_mode == "percent"
                else cumulative_value + (value / 2)
            )
            center_share = cumulative_share + (share / 2)
            label_text = (
                f"{share:.0f}"
                if value_mode == "percent"
                else f"{_format_absolute_value(value, value_display_divisor)} ({share:.0f}%)"
            )
            max_period = max_period_by_label.get(label)
            max_share = max_share_by_label.get(label, 0.0)
            if (
                max_period is not None
                and period == max_period
                and max_share >= series_name_min_share
                and label not in series_name_added
            ):
                if center_share >= 80.0:
                    label_text = f"{label}<br>{label_text}"
                else:
                    label_text = f"{label_text}<br>{label}"
                series_name_added.add(label)
            if value_mode == "percent":
                if period == first_period and period != last_period:
                    annotation_x = 0.01
                    annotation_xref = "paper"
                    annotation_xanchor = "left"
                elif period == last_period and period != first_period:
                    annotation_x = 0.99
                    annotation_xref = "paper"
                    annotation_xanchor = "right"
                else:
                    annotation_x = period
                    annotation_xref = "x"
                    annotation_xanchor = "center"
            else:
                annotation_x = period
                annotation_xref = "x"
                annotation_xanchor = "center"
            fig.add_annotation(
                text=label_text,
                x=annotation_x,
                y=y_pos,
                xref=annotation_xref,
                yref="y",
                showarrow=False,
                align="center",
                xanchor=annotation_xanchor,
                font=dict(color=_AREA_LABEL_COLOR, size=11),
            )
            cumulative_share += share
            cumulative_value += value

    if value_mode == "absolute":
        totals_by_period = {
            period: sum(period_value_map.get(period, {}).values()) for period in periods
        }
        if totals_by_period:
            first_period = periods[0]
            last_period = periods[-1]
            min_period = min(
                periods, key=lambda period: totals_by_period.get(period, 0.0)
            )
            max_period = max(
                periods, key=lambda period: totals_by_period.get(period, 0.0)
            )

            period_roles: dict[object, list[str]] = {}
            for period, role in (
                (first_period, "Initial"),
                (last_period, "Final"),
                (min_period, "Min"),
                (max_period, "Max"),
            ):
                period_roles.setdefault(period, []).append(role)

            for period in periods:
                if period not in period_roles:
                    continue
                total_value = totals_by_period.get(period, 0.0)
                if total_value <= 0:
                    continue
                label_text = f"{_format_absolute_value(total_value, value_display_divisor)} (100%)"
                fig.add_annotation(
                    text=label_text,
                    x=period,
                    y=total_value,
                    xref="x",
                    yref="y",
                    showarrow=False,
                    yanchor="bottom",
                    yshift=8,
                    align="center",
                    xanchor="center",
                    font=dict(color="#111827", size=11),
                )


def build_pipeline_area(
    df: pl.DataFrame,
    dimension: str,
    metric_column: str,
    period_column: str,
    *,
    palette: str | None = None,
    value_mode: Literal["percent", "absolute"] = "percent",
    value_display_divisor: float = 1.0,
    highlighted_items: list[str] | None = None,
    show_value_labels: bool = True,
) -> go.Figure:
    """Build a stacked area chart using the pipeline charting utilities."""
    naming = get_naming_params()
    if df.is_empty():
        raise ValueError("No data to plot.")

    lf = ensure_lazyframe(df)
    cols, _ = get_schema_and_column_names(lf)
    for required in (dimension, metric_column, period_column):
        if required not in cols:
            raise ValueError(f"Missing required column for area chart: {required}")

    top_items = _select_top_items(
        lf, dimension, metric_column, max_keep=_AUTO_MAX_KEEP_X
    )
    if not top_items:
        raise ValueError("No data to plot.")

    top_set = set(top_items)
    aggregate_other = len(top_set) < int(
        lf.select(pl.col(dimension).n_unique()).collect().item()
    )
    other_label = "Other"
    has_existing_other = any(str(item).strip().lower() == "other" for item in top_items)
    if aggregate_other and has_existing_other:
        other_label = "Other (aggregated)"

    df_plot = ensure_polars_df(lf)
    if aggregate_other:
        df_plot = (
            df_plot.with_columns(
                pl.when(pl.col(dimension).cast(pl.Utf8).is_in(list(top_set)))
                .then(pl.col(dimension))
                .otherwise(pl.lit(other_label))
                .alias(dimension)
            )
            .group_by([period_column, dimension])
            .agg(pl.col(metric_column).sum().alias(metric_column))
        )
        unique_items = [*top_items, other_label]
        aggregate_other_name = other_label
    else:
        unique_items = top_items
        aggregate_other_name = ""

    deduped_items: list[str] = []
    seen_items: set[str] = set()
    for item in unique_items:
        label = str(item).strip()
        if not label:
            continue
        key = label.lower()
        if key in seen_items:
            continue
        seen_items.add(key)
        deduped_items.append(label)
    unique_items = deduped_items

    plot_values_choice = (
        naming["percentOfResultRow"] if value_mode == "percent" else naming["absolute"]
    )
    chart_dict = {
        naming["chosenChart"]: naming["areaChart"],
        naming["plotValuesAsChoice"]: plot_values_choice,
        naming["showValueLabels"]: False,
    }
    if highlighted_items:
        deduped_highlights: list[str] = []
        seen_highlights: set[str] = set()
        for item in highlighted_items:
            label = str(item or "").strip()
            if not label:
                continue
            token = label.lower()
            if token in seen_highlights:
                continue
            seen_highlights.add(token)
            deduped_highlights.append(label)
        if deduped_highlights:
            chart_dict[naming["highlightedDimension"]] = deduped_highlights
    normalized_palette = _normalize_palette_name(palette, naming)
    if normalized_palette:
        chart_dict[naming["colorpalette"]] = normalized_palette

    fig, _df_export = draw_area_chart(
        df_plot,
        {},
        dimension,
        metric_column,
        period_column,
        chart_dict,
        0,
        unique_items,
        aggregate_other_name,
    )
    fig = update_area_chart_layout(fig, naming["areaChart"])
    if show_value_labels:
        _add_value_labels(
            fig,
            df_plot,
            dimension,
            metric_column,
            period_column,
            unique_items,
            value_mode=value_mode,
            value_display_divisor=value_display_divisor,
        )
    return fig
