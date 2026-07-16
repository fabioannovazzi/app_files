from __future__ import annotations

import logging
import re

import plotly.graph_objects as go
import polars as pl

from modules.charting.draw_width_and_stacked_plots import (
    _center_subplot_titles,
    _update_small_multiple_mekko_axes,
    mekko_plot,
    prepare_small_multiple_mekko_df,
)
from modules.charting.small_multiples_ordering import (
    order_small_multiple_facets_by_total as _order_small_multiple_facets_by_total,
)
from modules.charting.setup_fig import setup_fig_for_mekko_charts
from modules.data.common_data_utils import show_only_largest
from modules.data.multidimensional_charts_prep import prepare_data_for_width_plot
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import check_if_periods_in_columns
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_row_count,
    get_schema_and_column_names,
    is_valid_lazyframe,
)

__all__ = [
    "apply_barmekko_display_layout",
    "build_pipeline_barmekko",
    "build_pipeline_mekko",
]

_AUTO_MIN_SHARE = 0.01
_AUTO_CUMULATIVE_SHARE = 0.95
_AUTO_MIN_KEEP = 2
_AUTO_MAX_KEEP_X = 8
_AUTO_MAX_KEEP_W = 12
_MIN_TWO_LINE_ROW_SHARE = 0.08
_Y_LABEL_PAD = 0.01
_TOTAL_ARROW_Y = 0.9
_BARMEKKO_VALUE_LABEL_FONT_SIZE = 12
_BARMEKKO_MIN_ROW_SHARE_FOR_LABEL = 0.02
_BARMEKKO_MIN_X_SHARE_FOR_INSIDE_LABEL = 0.04

_LOGGER = logging.getLogger(__name__)


def _axis_limits(naming: dict, count: int) -> dict:
    return {
        naming["numberOfTop"]: count,
        naming["aggregateOtherItems"]: False,
    }


def _unique_count(lf: pl.LazyFrame, column: str) -> int:
    cols, _ = get_schema_and_column_names(lf)
    if column not in cols:
        return 0
    return int(lf.select(pl.col(column).n_unique().alias("count")).collect().item())


def _normalize_palette_name(palette: str | None, naming: dict) -> str | None:
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


def _auto_top_count(
    lf: pl.LazyFrame,
    dimension: str,
    metric_column: str,
    *,
    min_share: float = _AUTO_MIN_SHARE,
    cumulative_share: float = _AUTO_CUMULATIVE_SHARE,
    min_keep: int = _AUTO_MIN_KEEP,
    max_keep: int | None = None,
) -> int:
    cols, _ = get_schema_and_column_names(lf)
    if dimension not in cols or metric_column not in cols:
        return 0
    try:
        totals = (
            lf.group_by(dimension)
            .agg(pl.col(metric_column).sum().alias("__total"))
            .collect()
        )
    except (pl.exceptions.PolarsError, TypeError, ValueError):
        _LOGGER.exception("Auto-aggregation failed while computing totals.")
        return 0
    if totals.is_empty():
        return 0
    try:
        total_sum = float(totals.get_column("__total").sum())
    except (TypeError, ValueError):
        _LOGGER.exception("Auto-aggregation failed while summing totals.")
        return 0
    if total_sum <= 0:
        count = totals.height
        if max_keep is not None and max_keep > 0:
            count = min(count, max_keep)
        return count
    totals = totals.sort("__total", descending=True)
    shares = (totals.get_column("__total") / total_sum).to_list()
    count = 0
    cumulative = 0.0
    keep_floor = min_keep if totals.height >= min_keep else totals.height
    for share in shares:
        if count < keep_floor:
            cumulative += float(share)
            count += 1
            continue
        if share < min_share or cumulative >= cumulative_share:
            break
        cumulative += float(share)
        count += 1
    final_count = max(count, keep_floor)
    if max_keep is not None and max_keep > 0:
        final_count = min(final_count, max_keep)
    return min(final_count, totals.height)


def _apply_auto_axis_aggregation(
    lf: pl.LazyFrame,
    chart_dict: dict,
    naming: dict,
    x_dim: str,
    y_dim: str,
    metric_column: str,
) -> None:
    cols, _ = get_schema_and_column_names(lf)
    for axis_key, dimension in [("X", x_dim), ("W", y_dim)]:
        if dimension not in cols:
            continue
        if axis_key not in chart_dict or not isinstance(chart_dict[axis_key], dict):
            continue
        unique_count = _unique_count(lf, dimension)
        if unique_count <= 0:
            continue
        existing_top = chart_dict[axis_key].get(naming["numberOfTop"], unique_count)
        if existing_top < unique_count:
            continue
        max_keep = _AUTO_MAX_KEEP_X if axis_key == "X" else _AUTO_MAX_KEEP_W
        number_of_top = _auto_top_count(
            lf,
            dimension,
            metric_column,
            max_keep=max_keep,
        )
        if number_of_top <= 0:
            number_of_top = unique_count
        number_of_top = min(number_of_top, unique_count)
        chart_dict[axis_key][naming["numberOfTop"]] = number_of_top
        chart_dict[axis_key][naming["aggregateOtherItems"]] = (
            number_of_top < unique_count
        )


def _apply_mekko_label_format(
    fig: go.Figure,
    *,
    include_trace_label: bool = True,
    percent_from_area: bool = False,
) -> None:
    panel_width_totals: dict[tuple[str, str], float] = {}
    panel_area_totals: dict[tuple[str, str], float] = {}
    for trace in fig.data:
        if getattr(trace, "type", None) != "bar":
            continue
        width_vals = trace.width
        panel_key = (
            getattr(trace, "xaxis", "x") or "x",
            getattr(trace, "yaxis", "y") or "y",
        )
        x_vals = trace.x
        if not isinstance(width_vals, (list, tuple)):
            continue
        if panel_key not in panel_width_totals:
            try:
                panel_width_totals[panel_key] = float(
                    sum(float(v or 0.0) for v in width_vals)
                )
            except (TypeError, ValueError):
                panel_width_totals[panel_key] = 0.0
        if not isinstance(x_vals, (list, tuple)) or len(x_vals) != len(width_vals):
            continue
        area_sum = 0.0
        for width_val, x_val in zip(width_vals, x_vals):
            try:
                area_sum += float(width_val or 0.0) * float(x_val or 0.0)
            except (TypeError, ValueError):
                continue
        panel_area_totals[panel_key] = panel_area_totals.get(panel_key, 0.0) + area_sum
    total_map = panel_area_totals if percent_from_area else panel_width_totals
    global_total = float(sum(total_map.values())) if total_map else 0.0
    # Small-multiple panels have less horizontal room, so be stricter about two-line labels.
    min_share = _MIN_TWO_LINE_ROW_SHARE * (2 if len(total_map) > 1 else 1)

    for trace in fig.data:
        if getattr(trace, "type", None) != "bar":
            continue
        text_vals = trace.text
        x_vals = trace.x
        width_vals = trace.width
        if not isinstance(text_vals, (list, tuple)) or not isinstance(
            x_vals, (list, tuple)
        ):
            continue
        if len(text_vals) != len(x_vals):
            continue
        if (
            width_vals is not None
            and isinstance(width_vals, (list, tuple))
            and len(width_vals) != len(x_vals)
        ):
            width_vals = None
        label = trace.name or ""
        panel_key = (
            getattr(trace, "xaxis", "x") or "x",
            getattr(trace, "yaxis", "y") or "y",
        )
        panel_total = panel_width_totals.get(panel_key, 0.0)
        formatted = []
        for idx, (raw_text, raw_x) in enumerate(zip(text_vals, x_vals)):
            abs_val = "" if raw_text is None else str(raw_text)
            pct_val = None
            width_share = None
            if width_vals is not None and panel_total > 0 and len(width_vals) > idx:
                try:
                    width_share = float(width_vals[idx] or 0.0) / panel_total
                except (TypeError, ValueError, ZeroDivisionError):
                    width_share = None
            use_two_lines = True
            if width_share is not None and width_share < min_share:
                use_two_lines = False
            if width_vals is not None and global_total > 0:
                try:
                    width_val = float(width_vals[idx] or 0.0)
                    share_val = float(raw_x or 0.0)
                    pct_val = (width_val * share_val / global_total) * 100.0
                except (TypeError, ValueError):
                    pct_val = None
            if pct_val is None and raw_x is not None:
                try:
                    pct_val = float(raw_x)
                    if pct_val <= 1 and global_total == 0:
                        pct_val *= 100
                except (TypeError, ValueError):
                    pct_val = None
            pct_text = ""
            if pct_val is not None:
                pct_text = f"{pct_val:.1f}".rstrip("0").rstrip(".")
            pct_display = f"{pct_text}%" if pct_text else ""
            if label and include_trace_label:
                if abs_val and pct_display:
                    if use_two_lines:
                        formatted.append(f"{label}<br>{abs_val} ({pct_display})")
                    else:
                        formatted.append(label)
                elif abs_val:
                    formatted.append(
                        f"{label}<br>{abs_val}" if use_two_lines else label
                    )
                elif pct_display:
                    formatted.append(
                        f"{label}<br>({pct_display})" if use_two_lines else label
                    )
                else:
                    formatted.append(label)
            else:
                if abs_val and pct_display:
                    formatted.append(f"{abs_val} ({pct_display})")
                elif abs_val:
                    formatted.append(abs_val)
                elif pct_display:
                    formatted.append(f"({pct_display})")
                else:
                    formatted.append("")
        trace.text = formatted
        trace.hovertext = formatted


def _is_numeric_text_label(text: str | None) -> bool:
    if text is None:
        return False
    plain = re.sub(r"<[^>]+>", "", str(text)).strip()
    if not plain:
        return False
    return bool(re.match(r"^-?\d", plain))


def _strip_percent_suffix(text: str | None) -> str:
    if text is None:
        return ""
    plain = re.sub(r"<[^>]+>", "", str(text)).strip()
    return re.sub(r"\s*\([^)]+%\)\s*$", "", plain).strip()


def _format_pct(pct_value: float) -> str:
    pct_text = f"{pct_value:.1f}".rstrip("0").rstrip(".")
    return f"{pct_text}%"


def _build_barmekko_row_geometry(trace: go.Bar) -> list[dict[str, float]]:
    x_vals = trace.x
    y_vals = trace.y
    width_vals = trace.width
    if not isinstance(x_vals, (list, tuple)):
        return []
    if not isinstance(y_vals, (list, tuple)):
        return []
    if not isinstance(width_vals, (list, tuple)):
        return []
    if len(x_vals) != len(y_vals) or len(y_vals) != len(width_vals):
        return []
    if len(x_vals) == 0:
        return []
    try:
        total_width = float(sum(float(v or 0.0) for v in width_vals))
    except (TypeError, ValueError):
        return []
    if total_width <= 0:
        return []
    x_abs_values: list[float] = []
    for value in x_vals:
        try:
            x_abs_values.append(abs(float(value or 0.0)))
        except (TypeError, ValueError):
            x_abs_values.append(0.0)
    x_max = max(x_abs_values) if x_abs_values else 0.0
    row_values: list[tuple[float, float, float]] = []
    total_area = 0.0
    for x_val, y_val, width_val in zip(x_abs_values, y_vals, width_vals):
        try:
            width_num = float(width_val or 0.0)
            center = float(y_val or 0.0) + width_num / 2.0
        except (TypeError, ValueError):
            continue
        area_value = width_num * x_val
        total_area += area_value
        row_values.append((center, width_num, x_val))
    rows: list[dict[str, float]] = []
    for center, width_num, x_val in row_values:
        row_share = width_num / total_width if total_width > 0 else 0.0
        x_share = (x_val / x_max) if x_max > 0 else 0.0
        area_share = (width_num * x_val / total_area) if total_area > 0 else 0.0
        rows.append(
            {
                "center": center,
                "row_share": row_share,
                "x_share": x_share,
                "area_share": area_share,
            }
        )
    return rows


def _enforce_barmekko_value_labels(fig: go.Figure) -> None:
    rows_by_axis: dict[str, list[dict[str, float]]] = {}
    for trace in fig.data:
        if getattr(trace, "type", None) != "bar":
            continue
        axis_key = getattr(trace, "yaxis", "y") or "y"
        row_geometry = _build_barmekko_row_geometry(trace)
        if row_geometry and axis_key not in rows_by_axis:
            rows_by_axis[axis_key] = row_geometry
        text_vals = trace.text
        if (
            isinstance(text_vals, (list, tuple))
            and row_geometry
            and len(text_vals) == len(row_geometry)
        ):
            filtered_text: list[str] = []
            for raw_text, row in zip(text_vals, row_geometry):
                keep = row["row_share"] >= _BARMEKKO_MIN_ROW_SHARE_FOR_LABEL
                filtered_text.append(_strip_percent_suffix(raw_text) if keep else "")
            trace.text = filtered_text
            trace.hovertext = filtered_text
        existing_textfont = (
            trace.textfont.to_plotly_json()
            if getattr(trace, "textfont", None) is not None
            else {}
        )
        trace.textfont = {
            **existing_textfont,
            "size": _BARMEKKO_VALUE_LABEL_FONT_SIZE,
        }
        trace.textangle = 0

    if fig.layout.annotations:
        for ann in fig.layout.annotations:
            xref = str(getattr(ann, "xref", "") or "")
            yref = str(getattr(ann, "yref", "") or "")
            if not yref.startswith("y"):
                continue
            if xref not in {"x", "x domain"}:
                continue
            if not _is_numeric_text_label(getattr(ann, "text", None)):
                continue
            row_geometry = rows_by_axis.get(yref)
            if row_geometry:
                try:
                    y_value = float(getattr(ann, "y"))
                except (TypeError, ValueError):
                    y_value = 0.0
                nearest = min(
                    row_geometry, key=lambda row: abs(row["center"] - y_value)
                )
                keep = nearest["row_share"] >= _BARMEKKO_MIN_ROW_SHARE_FOR_LABEL
                if xref == "x":
                    keep = (
                        keep
                        and nearest["x_share"] >= _BARMEKKO_MIN_X_SHARE_FOR_INSIDE_LABEL
                    )
                if not keep:
                    ann.text = ""
                elif xref == "x":
                    base_value = _strip_percent_suffix(getattr(ann, "text", None))
                    ann.text = (
                        f"{base_value} ({_format_pct(nearest['area_share'] * 100.0)})"
                    )
            ann_font = (
                ann.font.to_plotly_json()
                if getattr(ann, "font", None) is not None
                else {}
            )
            ann.font = {**ann_font, "size": _BARMEKKO_VALUE_LABEL_FONT_SIZE}

    existing_uniformtext = (
        fig.layout.uniformtext.to_plotly_json()
        if getattr(fig.layout, "uniformtext", None) is not None
        else {}
    )
    fig.update_layout(
        uniformtext={
            **existing_uniformtext,
            "mode": "hide",
            "minsize": _BARMEKKO_VALUE_LABEL_FONT_SIZE,
        }
    )


def _normalize_title(text: str | None) -> str:
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", "", str(text))
    return stripped.strip().lower()


def _promote_yaxis_labels_to_annotations(
    fig: go.Figure, x_pad: float = _Y_LABEL_PAD
) -> None:
    layout_dict = fig.to_plotly_json().get("layout", {})
    annotations = list(fig.layout.annotations) if fig.layout.annotations else []
    for axis_key in sorted(k for k in layout_dict if k.startswith("yaxis")):
        axis = fig.layout[axis_key]
        tickvals = getattr(axis, "tickvals", None)
        ticktext = getattr(axis, "ticktext", None)
        if not tickvals or not ticktext:
            continue
        anchor = getattr(axis, "anchor", None) or "x"
        xaxis_key = "xaxis" if anchor == "x" else f"xaxis{anchor[1:]}"
        xaxis = fig.layout[xaxis_key] if xaxis_key in layout_dict else None
        domain = getattr(xaxis, "domain", None) if xaxis else None
        x_pos = (domain[0] - x_pad) if domain and len(domain) == 2 else 0.0
        if x_pos < -0.005:
            x_pos = -0.005
        yref = "y" if axis_key == "yaxis" else axis_key.replace("axis", "")
        for val, label in zip(tickvals, ticktext):
            annotations.append(
                dict(
                    x=x_pos,
                    y=val,
                    xref="paper",
                    yref=yref,
                    text=str(label),
                    showarrow=False,
                    xanchor="right",
                    align="right",
                )
            )
        axis.update(showticklabels=False)
    fig.update_layout(annotations=annotations)


def _add_total_percent_arrow(fig: go.Figure, percent: float = 100.0) -> None:
    return


def _sort_mekko_columns_by_total(
    df: pl.DataFrame,
    color_array: list[str],
    x_dimension: str,
    naming: dict,
) -> tuple[pl.DataFrame, list[str]]:
    columns, _ = get_schema_and_column_names(df)
    if not columns or len(columns) <= 2:
        return df, color_array
    if x_dimension in columns:
        value_cols = [c for c in columns if c != x_dimension]
    else:
        x_dimension = columns[0]
        value_cols = columns[1:]
    if not value_cols:
        return df, color_array
    aggregate_prefix = str(naming["aggregateOtherItemsName"])

    def _is_other_label(label: str) -> bool:
        lower = label.strip().lower()
        return lower == "other" or lower == "other (aggregated)"

    other_cols = []
    for c in value_cols:
        if not isinstance(c, str):
            continue
        if aggregate_prefix and c.startswith(aggregate_prefix):
            other_cols.append(c)
            continue
        if _is_other_label(c):
            other_cols.append(c)
    regular_cols = [c for c in value_cols if c not in other_cols]
    if not regular_cols:
        return df, color_array
    sums_df = df.select([pl.col(c).sum().alias(c) for c in regular_cols])
    sums = sums_df.to_dicts()[0] if sums_df.height else {}
    sorted_regular = sorted(regular_cols, key=lambda c: sums.get(c, 0.0), reverse=True)
    ordered_cols = sorted_regular + other_cols
    if ordered_cols == value_cols:
        return df, color_array
    color_map = {
        col: color_array[idx]
        for idx, col in enumerate(value_cols)
        if idx < len(color_array)
    }
    new_colors = [color_map.get(col) for col in ordered_cols if col in color_map]
    if len(new_colors) < len(color_array):
        new_colors += color_array[len(new_colors) :]
    new_df = df.select([x_dimension] + ordered_cols)
    return new_df, new_colors


def _rename_aggregate_labels(
    df: pl.DataFrame,
    x_dimension: str,
    naming: dict,
) -> pl.DataFrame:
    columns, _ = get_schema_and_column_names(df)
    aggregate_prefix = str(naming["aggregateOtherItemsName"])
    if not aggregate_prefix:
        return df
    has_other = False
    if x_dimension in columns:
        try:
            values = (
                df.select(pl.col(x_dimension).unique())
                .get_column(x_dimension)
                .to_list()
            )
            has_other = any(str(v).strip().lower() == "other" for v in values)
        except Exception:
            has_other = False
    if not has_other:
        for col in columns:
            if col != x_dimension and isinstance(col, str):
                if col.strip().lower() == "other":
                    has_other = True
                    break
    replacement = "Other (aggregated)" if has_other else "Other"
    rename_map = {
        col: replacement
        for col in columns
        if col != x_dimension
        and isinstance(col, str)
        and col.startswith(aggregate_prefix)
    }
    if rename_map:
        df = df.rename(rename_map)
    if x_dimension in columns:
        df = df.with_columns(
            pl.when(pl.col(x_dimension).cast(pl.Utf8).str.starts_with(aggregate_prefix))
            .then(pl.lit(replacement))
            .otherwise(pl.col(x_dimension))
            .alias(x_dimension)
        )
    return df


def _build_base_chart_dict(
    naming: dict,
    x_dim: str,
    y_dim: str,
    metric: str,
    period: str,
    x_count: int,
    y_count: int,
    *,
    small_multiples: bool,
    facet_dim: str | None,
    facet_count: int,
) -> dict:
    chart_dict = {
        naming["chosenChart"]: naming["marimekkoChart"],
        naming["xAxisDimension"]: x_dim,
        naming["yAxisDimension"]: y_dim,
        naming["singleMetric"]: metric,
        naming["xAxisMetric"]: metric,
        naming["yAxisMetric"]: metric,
        naming["showLegend"]: naming["showLegendOnTop"],
        naming["showValuesAs"]: naming["absolute"],
        naming["aggregateOtherItemsName"]: "",
        naming["plotSmallMultiplesOtherCharts"]: small_multiples,
        naming["selectedPeriods"]: [period],
        naming["toPlotPeriod"]: period,
        "X": _axis_limits(naming, x_count),
        "W": _axis_limits(naming, y_count),
    }
    if small_multiples:
        chart_dict[naming["smallMultiplesColumn"]] = facet_dim
        chart_dict["Y"] = _axis_limits(naming, facet_count)
    return chart_dict


def build_pipeline_mekko(
    df: pl.DataFrame,
    x_dimension: str,
    y_dimension: str,
    metric_column: str,
    period: str,
    *,
    small_multiples: bool = False,
    facet_dimension: str | None = None,
    palette: str | None = None,
    small_multiples_count: int | None = None,
) -> tuple[go.Figure, list[str]]:
    """Build a marimekko chart using the legacy charting pipeline without UI hooks."""
    naming = get_naming_params()
    period_col = naming["periodName"]
    value_name = naming["valueName"]
    figure_name = naming["figureName"]
    row_name = naming["rowName"]
    col_name = naming["columnName"]
    small_multiples_dimension_key = naming["smallMultiplesDimension"]

    lf = ensure_lazyframe(df)
    cols, _ = get_schema_and_column_names(lf)
    for required in (x_dimension, y_dimension, metric_column):
        if required not in cols:
            raise ValueError(f"Missing required column for Mekko: {required}")
    if small_multiples:
        if not facet_dimension:
            raise ValueError(
                "facet_dimension is required for small-multiple Mekko charts."
            )
        if facet_dimension not in cols:
            raise ValueError(f"Missing facet column for Mekko: {facet_dimension}")

    if period_col not in cols:
        lf = lf.with_columns(pl.lit(period).alias(period_col))
    lf = lf.with_columns(pl.col(period_col).cast(pl.Utf8))
    lf, period = check_if_periods_in_columns(lf, period)
    lf = lf.filter(pl.col(period_col) == period)

    if get_row_count(lf) == 0:
        raise ValueError("No data to plot.")

    monetary_name = naming["monetaryLocalCurrencyName"]
    cols, _ = get_schema_and_column_names(lf)
    if monetary_name not in cols:
        lf = lf.with_columns(pl.col(metric_column).alias(monetary_name))
        cols, _ = get_schema_and_column_names(lf)

    x_count = _unique_count(lf, x_dimension)
    y_count = _unique_count(lf, y_dimension)
    facet_count = _unique_count(lf, facet_dimension) if small_multiples else 0
    if x_count == 0 or y_count == 0 or (small_multiples and facet_count == 0):
        raise ValueError("No data to plot.")

    chart_dict = _build_base_chart_dict(
        naming,
        x_dimension,
        y_dimension,
        metric_column,
        period,
        x_count,
        y_count,
        small_multiples=small_multiples,
        facet_dim=facet_dimension,
        facet_count=facet_count,
    )
    if small_multiples:
        chart_dict[naming["showLegend"]] = naming["notMetConditionValue"]
    if small_multiples:
        target_panels = facet_count
        if small_multiples_count is not None:
            try:
                target_panels = int(small_multiples_count)
            except (TypeError, ValueError):
                target_panels = facet_count
        target_panels = max(1, min(target_panels, facet_count))
        if target_panels < facet_count and target_panels > 1:
            chart_dict["Y"][naming["numberOfTop"]] = max(target_panels - 1, 1)
            chart_dict["Y"][naming["aggregateOtherItems"]] = True
        else:
            chart_dict["Y"][naming["numberOfTop"]] = target_panels
            chart_dict["Y"][naming["aggregateOtherItems"]] = False
    palette_key = _normalize_palette_name(palette, naming)
    if palette_key:
        chart_dict[naming["colorpalette"]] = palette_key
    _apply_auto_axis_aggregation(
        lf,
        chart_dict,
        naming,
        x_dimension,
        y_dimension,
        metric_column,
    )

    param_dict: dict = {}
    used_color_dict: dict = {}
    warnings: list[str] = []
    value_cols = [metric_column]

    if not small_multiples:
        (
            df_filtered,
            _metric_to_plot,
            color_array,
            used_color_dict,
            chart_dict,
            _period,
            _,
        ) = prepare_data_for_width_plot(
            lf, period, value_cols, chart_dict, param_dict, used_color_dict
        )
        df_filtered = ensure_polars_df(df_filtered)
        if get_row_count(df_filtered) == 0:
            raise ValueError("No data to plot.")
        df_filtered, color_array = _sort_mekko_columns_by_total(
            df_filtered, color_array, x_dimension, naming
        )
        df_filtered = _rename_aggregate_labels(df_filtered, x_dimension, naming)
        fig, _df_negative, negative_message, chart_dict = mekko_plot(
            df_filtered,
            chart_dict,
            param_dict,
            unit_name=value_name,
            colors=color_array,
        )
        if negative_message:
            warnings.append(negative_message)
        _apply_mekko_label_format(fig)
        _promote_yaxis_labels_to_annotations(fig)
        _add_total_percent_arrow(fig, 100.0)
        return fig, warnings

    _df_dump, second_dimension_items, _agg_other, value_cols = show_only_largest(
        lf,
        facet_dimension,
        chart_dict[naming["xAxisDimension"]],
        period_col,
        value_cols,
        chart_dict,
        param_dict,
        "Y",
    )
    _df_dump, global_unique_items, _global_agg_other, value_cols = show_only_largest(
        lf,
        chart_dict[naming["xAxisDimension"]],
        None,
        period_col,
        value_cols,
        chart_dict,
        param_dict,
        "X",
    )
    second_dimension_items = [
        str(item).strip()
        for item in second_dimension_items
        if item is not None and str(item).strip()
    ]
    if not second_dimension_items:
        raise ValueError("No facet values to plot.")
    aggregate_prefix = str(naming["aggregateOtherItemsName"])
    aggregate_label = None
    for item in second_dimension_items:
        if isinstance(item, str) and item.startswith(aggregate_prefix):
            aggregate_label = item
            break
    if aggregate_label:
        other_labels = {
            str(item).strip().lower()
            for item in second_dimension_items
            if item is not None and item != aggregate_label
        }
        replacement = (
            "Other (aggregated)"
            if "other" in other_labels or "others" in other_labels
            else "Other"
        )
        if replacement != aggregate_label:
            lf = lf.with_columns(
                pl.when(pl.col(facet_dimension) == aggregate_label)
                .then(pl.lit(replacement))
                .otherwise(pl.col(facet_dimension))
                .alias(facet_dimension)
            )
            second_dimension_items = [
                replacement if item == aggregate_label else item
                for item in second_dimension_items
            ]
    second_dimension_items = _order_small_multiple_facets_by_total(
        lf,
        facet_dimension,
        metric_column,
        second_dimension_items,
        aggregate_prefix,
    )
    chart_dict[naming["numberOfPlottedSmallMultiples"]] = len(second_dimension_items)

    param_dict, number_of_cols, _number_of_rows = setup_fig_for_mekko_charts(
        df,
        facet_dimension,
        second_dimension_items,
        chart_dict[naming["xAxisDimension"]],
        param_dict,
        chart_dict,
    )
    fig = param_dict[figure_name]
    chart_dict[small_multiples_dimension_key] = None
    chart_dict[row_name], chart_dict[col_name] = 1, 1

    for idx, dimension in enumerate(second_dimension_items):
        row = idx // number_of_cols + 1
        col = idx % number_of_cols + 1
        chart_dict[row_name] = row
        chart_dict[col_name] = col
        chart_dict[small_multiples_dimension_key] = dimension
        (
            lf_plot,
            _metric_to_plot,
            color_array,
            used_color_dict,
            chart_dict,
            _period,
        ) = prepare_small_multiple_mekko_df(
            lf,
            dimension,
            second_dimension_items,
            facet_dimension,
            value_cols,
            chart_dict,
            param_dict,
            used_color_dict,
            period_col,
            global_unique_items,
        )
        if not is_valid_lazyframe(lf_plot):
            continue
        columns, _ = get_schema_and_column_names(lf_plot)
        cols_to_use = [c for c in columns if c != facet_dimension]
        df_panel = ensure_polars_df(lf_plot.select(cols_to_use))
        df_panel, color_array = _sort_mekko_columns_by_total(
            df_panel, color_array, x_dimension, naming
        )
        df_panel = _rename_aggregate_labels(df_panel, x_dimension, naming)
        fig, _df_negative, negative_message, chart_dict = mekko_plot(
            df_panel,
            chart_dict,
            param_dict,
            unit_name=value_name,
            colors=color_array,
        )
        if negative_message:
            warnings.append(negative_message)

    _update_small_multiple_mekko_axes(
        fig, naming["marimekkoChart"], naming["barmekkoChart"], 0.0
    )
    _center_subplot_titles(fig, second_dimension_items)
    _apply_mekko_label_format(fig)
    _promote_yaxis_labels_to_annotations(fig)
    return fig, warnings


def build_pipeline_barmekko(
    df: pl.DataFrame,
    x_dimension: str,
    sales_column: str,
    units_column: str,
    period: str,
    *,
    palette: str | None = None,
) -> tuple[go.Figure, list[str]]:
    """Build a barmekko chart where width=units and height=unit price."""
    naming = get_naming_params()
    period_col = naming["periodName"]
    value_name = naming["valueName"]
    chosen_chart_key = naming["chosenChart"]
    barmekko_chart = naming["barmekkoChart"]
    x_axis_dimension_key = naming["xAxisDimension"]
    y_axis_dimension_key = naming["yAxisDimension"]
    x_axis_metric_key = naming["xAxisMetric"]
    y_axis_metric_key = naming["yAxisMetric"]
    monetary_name = naming["monetaryLocalCurrencyName"]
    units_name = naming["unitsName"]
    price_per_unit_name = naming["pricePerUnitName"]
    show_legend_key = naming["showLegend"]
    show_values_as_key = naming["showValuesAs"]
    aggregate_other_items_name_key = naming["aggregateOtherItemsName"]
    small_multiples_key = naming["plotSmallMultiplesOtherCharts"]
    small_multiples_column_key = naming["smallMultiplesColumn"]
    selected_periods_key = naming["selectedPeriods"]
    to_plot_period_key = naming["toPlotPeriod"]
    sort_axis_key = naming["sortAxis"]
    x_axis_sort = naming["xAxisSort"]

    lf = ensure_lazyframe(df)
    cols, _ = get_schema_and_column_names(lf)
    for required in (x_dimension, sales_column, units_column):
        if required not in cols:
            raise ValueError(f"Missing required column for barmekko: {required}")

    if period_col not in cols:
        lf = lf.with_columns(pl.lit(period).alias(period_col))
    lf = lf.with_columns(pl.col(period_col).cast(pl.Utf8))
    lf, period = check_if_periods_in_columns(lf, period)
    lf = lf.filter(pl.col(period_col) == period)
    if get_row_count(lf) == 0:
        raise ValueError("No data to plot.")

    lf = lf.with_columns(
        [
            pl.col(x_dimension).cast(pl.Utf8).fill_null("N/A").alias(x_dimension),
            pl.col(sales_column).cast(pl.Float64).fill_null(0.0).alias(monetary_name),
            pl.col(units_column).cast(pl.Float64).fill_null(0.0).alias(units_name),
        ]
    )
    x_count = _unique_count(lf, x_dimension)
    if x_count == 0:
        raise ValueError("No data to plot.")

    chart_dict = {
        chosen_chart_key: barmekko_chart,
        x_axis_dimension_key: x_dimension,
        # Keep this as a real dimension to avoid legacy width-plot fallback labels like "Value".
        y_axis_dimension_key: x_dimension,
        naming["singleMetric"]: monetary_name,
        naming["multipliedMetric"]: monetary_name,
        x_axis_metric_key: units_name,
        y_axis_metric_key: price_per_unit_name,
        show_legend_key: naming["showLegendOnTop"],
        show_values_as_key: naming["absolute"],
        aggregate_other_items_name_key: "",
        small_multiples_key: False,
        small_multiples_column_key: None,
        selected_periods_key: [period],
        to_plot_period_key: period,
        sort_axis_key: x_axis_sort,
        "X": _axis_limits(naming, x_count),
    }
    palette_key = _normalize_palette_name(palette, naming)
    if palette_key:
        chart_dict[naming["colorpalette"]] = palette_key
    _apply_auto_axis_aggregation(
        lf,
        chart_dict,
        naming,
        x_dimension,
        x_dimension,
        monetary_name,
    )

    param_dict: dict = {
        naming["volumeColFound"]: False,
        naming["unitsColFound"]: True,
        naming["discountColFound"]: False,
        naming["marginColFound"]: False,
        naming["monetaryLocalCurrencyColFound"]: True,
    }
    used_color_dict: dict = {}
    warnings: list[str] = []
    value_cols = [monetary_name, units_name]
    (
        df_filtered,
        _metric_to_plot,
        color_array,
        used_color_dict,
        chart_dict,
        _period,
        _,
    ) = prepare_data_for_width_plot(
        lf, period, value_cols, chart_dict, param_dict, used_color_dict
    )
    df_filtered = ensure_polars_df(df_filtered)
    if get_row_count(df_filtered) == 0:
        raise ValueError("No data to plot.")
    df_filtered = _rename_aggregate_labels(df_filtered, x_dimension, naming)
    fig, _df_negative, negative_message, chart_dict = mekko_plot(
        df_filtered, chart_dict, param_dict, unit_name=value_name, colors=color_array
    )
    if negative_message:
        warnings.append(negative_message)
    _apply_mekko_label_format(fig, include_trace_label=False, percent_from_area=True)
    _promote_yaxis_labels_to_annotations(fig)
    _enforce_barmekko_value_labels(fig)
    return fig, warnings


def apply_barmekko_display_layout(fig: go.Figure) -> None:
    """Apply the shared barmekko display geometry used by app and brief renders."""
    base_margin = (
        fig.layout.margin.to_plotly_json()
        if getattr(fig.layout, "margin", None) is not None
        else {}
    )
    bar_traces = [trace for trace in fig.data if getattr(trace, "type", None) == "bar"]
    min_bar_x = float("inf")
    max_bar_x = float("-inf")
    max_right_label_chars = 0

    for trace in bar_traces:
        trace.cliponaxis = False
        trace_text = getattr(trace, "text", None)
        if isinstance(trace_text, (list, tuple)):
            for text_val in trace_text:
                text_len = len(str(text_val or ""))
                if text_len > max_right_label_chars:
                    max_right_label_chars = text_len
        trace_x = getattr(trace, "x", None)
        if not isinstance(trace_x, (list, tuple)):
            continue
        for value in trace_x:
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            if num < min_bar_x:
                min_bar_x = num
            if num > max_bar_x:
                max_bar_x = num

    has_bar_extent = min_bar_x != float("inf") and max_bar_x != float("-inf")
    bar_span = max(0.001, max_bar_x - min_bar_x) if has_bar_extent else 0.0
    right_pad = (
        max(bar_span * 0.25, max(abs(max_bar_x), 1.0) * 0.08) if has_bar_extent else 0.0
    )
    x_range: list[float] | None = None
    if has_bar_extent:
        x_range = [min(0.0, min_bar_x - bar_span * 0.03), max_bar_x + right_pad]

    max_left_label_chars = 0
    for ann in list(fig.layout.annotations or []):
        ann_text = str(getattr(ann, "text", "") or "")
        xref = str(getattr(ann, "xref", "") or "")
        yref = str(getattr(ann, "yref", "") or "")
        xanchor = str(getattr(ann, "xanchor", "") or "")
        is_left_category_label = (
            xref == "paper"
            and yref.startswith("y")
            and xanchor == "right"
            and "(" not in ann_text
            and "<b>" not in ann_text
        )
        if is_left_category_label:
            max_left_label_chars = max(max_left_label_chars, len(ann_text))

    right_margin = max(
        int(base_margin.get("r") or 0),
        min(320, max(120, max_right_label_chars * 7)),
    )
    left_margin = max(
        int(base_margin.get("l") or 0),
        min(340, max(100, max_left_label_chars * 8 + 24)),
    )
    fig.update_layout(
        margin={
            "t": max(int(base_margin.get("t") or 0), 120),
            "r": right_margin,
            "b": int(base_margin.get("b") or 80),
            "l": left_margin,
            "pad": int(base_margin.get("pad") or 0),
        },
        xaxis={
            **(
                fig.layout.xaxis.to_plotly_json()
                if getattr(fig.layout, "xaxis", None) is not None
                else {}
            ),
            "automargin": True,
            **({"range": x_range} if x_range is not None else {}),
        },
        yaxis={
            **(
                fig.layout.yaxis.to_plotly_json()
                if getattr(fig.layout, "yaxis", None) is not None
                else {}
            ),
            "automargin": True,
        },
    )
