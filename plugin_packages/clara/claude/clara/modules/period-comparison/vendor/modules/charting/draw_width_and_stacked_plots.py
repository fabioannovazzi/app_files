import copy
import logging
import math
import re

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

try:  # pragma: no cover - optional dependency during testing
    from modules.charting.adjust_position import (
        get_x_shift_for_data_column,
        move_labels_up,
        reset_height,
        set_bar_gap_offset,
    )
except ModuleNotFoundError as e:  # pragma: no cover - provide fallbacks
    from modules.utilities.ui_notifier import ui

    ui.write("adjust_position import error:", e)
    get_x_shift_for_data_column = lambda *a, **k: 0
    move_labels_up = lambda fig, *a, **k: fig
    reset_height = lambda fig, *a, **k: fig
    set_bar_gap_offset = lambda *a, **k: (0.0, 0.0, False)
from modules.charting.chart_helpers import (
    check_if_negative_values_in_mekko,
    set_up_tab_for_show_or_download_chart,
    show_total_percent,
)
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_title_as_annotation,
    enable_draw_shapes,
    get_color_array,
    get_color_dictionary,
    get_number_prefix,
    get_user_message,
    millify_dataframe,
    prepare_arrays_to_add_traces,
    reset_row_and_column_counters,
    set_other_color_to_grey,
)
from modules.charting.draw_charts_utils import (
    add_blank_column_for_data_column_annotations,
    add_cxgr_on_right,
    add_first_row_annotations,
    add_legends_on_left,
    add_legends_on_left_or_right,
    add_legends_on_top,
    add_overlay_trace,
    add_total_annotations,
    add_totals_below,
    add_values_to_data_column_on_right,
    adjust_tick_text,
    apply_marker_styles,
    calculate_marimekko_positions,
    check_small_multiples_total,
    compute_half_column,
    compute_positions,
    get_chart_scale,
    get_marimekko_positions,
    get_text_template,
    get_x_axis_total,
    get_y_axis_total,
    is_readable_mekko_row,
    keep_same_scale_for_all_plots,
    set_stacked_pareto_params_and_add_trace,
    split_main_and_data_column_dataframe,
)


def _column_max_value(frame, column: str):
    """Return a column max for eager or lazy Polars frames."""

    if isinstance(frame, pl.LazyFrame):
        result = frame.select(pl.col(column).max().alias(column)).collect()
        if result.is_empty():
            return None
        return result.get_column(column)[0]
    if isinstance(frame, pl.DataFrame):
        return frame.get_column(column).max()
    return frame[column].max()


def _normalize_title(text: str | None) -> str:
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", "", str(text))
    return stripped.strip().lower()


def _subplot_panel_domains(fig: go.Figure) -> list[tuple[float, float, float]]:
    panels: list[tuple[float, float, float]] = []
    for axis_name in fig.layout:
        if not str(axis_name).startswith("xaxis"):
            continue
        axis = getattr(fig.layout, axis_name, None)
        x_domain = getattr(axis, "domain", None)
        y_anchor = getattr(axis, "anchor", None)
        if not x_domain or len(x_domain) != 2 or not y_anchor:
            continue
        if y_anchor == "y":
            yaxis_name = "yaxis"
        elif str(y_anchor).startswith("y"):
            yaxis_name = f"yaxis{str(y_anchor)[1:]}"
        else:
            continue
        yaxis = getattr(fig.layout, yaxis_name, None)
        y_domain = getattr(yaxis, "domain", None) if yaxis else None
        if not y_domain or len(y_domain) != 2:
            continue
        x_left = float(x_domain[0])
        x_mid = (float(x_domain[0]) + float(x_domain[1])) / 2
        y_top = float(y_domain[1])
        panels.append((x_left, x_mid, y_top))
    return sorted(panels, key=lambda panel: (-round(panel[2], 12), panel[0]))


def _center_subplot_titles(fig: go.Figure, titles: list[str]) -> go.Figure:
    if not getattr(fig.layout, "annotations", None):
        return fig
    normalized_title_indexes: dict[str, int] = {}
    for index, title in enumerate(titles):
        normalized_title = _normalize_title(title)
        if normalized_title and normalized_title not in normalized_title_indexes:
            normalized_title_indexes[normalized_title] = index
    normalized_titles = set(normalized_title_indexes)
    panels = _subplot_panel_domains(fig)
    axis_mids: list[float] = []
    for axis_name in fig.layout:
        if not str(axis_name).startswith("xaxis"):
            continue
        axis = getattr(fig.layout, axis_name, None)
        domain = getattr(axis, "domain", None)
        if domain and len(domain) == 2:
            axis_mids.append((domain[0] + domain[1]) / 2)
    if not axis_mids:
        return fig
    axis_mids = sorted(set(round(mid, 12) for mid in axis_mids))
    title_annotations = []
    for ann in fig.layout.annotations:
        norm_text = _normalize_title(ann.text)
        is_known_title = bool(normalized_titles) and norm_text in normalized_titles
        is_top_label = (not normalized_titles) or (
            getattr(ann, "yref", "") == "paper"
            and float(getattr(ann, "y", 0) or 0) >= 1
            and "total" not in norm_text
        )
        if not (is_known_title or is_top_label):
            continue
        title_annotations.append(ann)

    use_ordered_domains = (
        len({round(float(getattr(ann, "x", 0) or 0), 6) for ann in title_annotations})
        <= 1
    )
    for index, ann in enumerate(title_annotations):
        norm_text = _normalize_title(ann.text)
        panel_index = normalized_title_indexes.get(norm_text)
        if panels and panel_index is None and index < len(panels):
            panel_index = index
        if panels and panel_index is not None and panel_index < len(panels):
            _x_left, x_mid, y_top = panels[panel_index]
            ann.x = x_mid
            ann.xref = "paper"
            ann.y = min(y_top + 0.008, 1)
            ann.yref = "paper"
            ann.yanchor = "bottom"
            ann.xanchor = "center"
            ann.align = "center"
            continue
        try:
            current_x = float(ann.x)
        except (TypeError, ValueError):
            current_x = axis_mids[0]
        closest_mid = (
            axis_mids[index % len(axis_mids)]
            if use_ordered_domains
            else min(axis_mids, key=lambda mid: abs(mid - current_x))
        )
        ann.x = closest_mid
        ann.xref = "paper"
        ann.xanchor = "center"
        ann.align = "center"
    return fig


def _update_small_multiple_mekko_axes(
    fig: go.Figure, chosen_chart: str, barmekko_chart: str, max_value: float
) -> go.Figure:
    """Scale each Mekko small-multiple panel locally.

    Small multiples compare structure first. The panel total annotation carries
    the absolute size, so forcing every panel to the largest panel's axis scale
    makes smaller panels unreadable without adding useful source context.
    """

    fig.for_each_yaxis(
        lambda axis: axis.update(
            matches=None,
            range=None,
            autorange=True,
            showticklabels=True,
        )
    )
    fig.for_each_xaxis(
        lambda axis: axis.update(
            matches=None,
            range=None,
            autorange=True,
            showticklabels=True,
        )
    )
    fig.update_xaxes(showticklabels=True)
    return fig


from modules.charting.make_titles import (
    make_marimekko_and_stacked_bar_chart_title,
    make_stacked_column_chart_title,
)
from modules.charting.polars_helpers import get_max_value, get_min_value, to_lists
from modules.charting.setup_fig import (
    setup_fig_for_mekko_charts,
    setup_fig_for_stacked_bar_charts,
    setup_fig_for_stacked_column_charts,
)
from modules.charting.small_multiples_ordering import (
    order_small_multiple_facets_by_total,
)
from modules.charting.update_layouts import (
    update_layout_bar_width_plot,
    update_stacked_bar_layout,
    update_stacked_column_layout,
    update_xaxes_bar_width_plot_horizontal,
    update_xaxes_bar_width_plot_vertical,
    update_yaxes_bar_width_plot_horizontal,
    update_yaxes_bar_width_plot_vertical,
)
from modules.data.common_data_utils import (
    get_cum_sum_dataframe,
    rank_others_as_last,
    show_only_largest,
)
from modules.data.multidimensional_charts_prep import (
    filter_small_multiples_dataframe,
    get_scaling_factor,
    prepare_data_for_stacked_column,
    prepare_data_for_width_plot,
    prepare_small_multiples_dataframe_for_stacked_bar,
)
from modules.layout.memoization import check_collect
from modules.plan.plan_dataset import modify_dataframe_for_Plan
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_app_message_to_paramdict,
    add_empty_dataset_error_message_in_plot_charts_tab,
    add_info_message_in_plot_charts_tab,
    add_warning_message_in_plot_charts_tab,
)
from modules.utilities.helpers import (
    change_index_names_if_cost_analysis,
    duplicate_dataframe,
    print_error_details,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_row_count,
    get_schema_and_column_names,
    is_valid_lazyframe,
)

try:  # pragma: no cover - optional dependency during testing
    from modules.charting.draw_charts_utils import drop_all_null_rows_lazy
except Exception as e:  # pragma: no cover - provide fallback
    ui.error("Something went wrong.")
    logging.exception(e)

    def drop_all_null_rows_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
        """Return ``lf`` unchanged when dependency is missing."""

        return lf


try:  # pragma: no cover - optional dependency during testing
    from modules.utilities.utils import percentage_cols_lazy
except Exception as e:  # pragma: no cover - provide fallback
    ui.error("Something went wrong.")
    logging.exception(e)

    def percentage_cols_lazy(
        lf: pl.LazyFrame, columns: list[str], value_name: str
    ) -> pl.LazyFrame:
        """Return ``lf`` unchanged when dependency is missing."""

        return lf


try:  # pragma: no cover - helper may be stubbed in tests
    from modules.utilities.helpers import is_numeric_dtype  # type: ignore
except Exception as e:  # pragma: no cover - provide fallback
    ui.error("Something went wrong.")
    logging.exception(e)

    def is_numeric_dtype(dt: pl.DataType) -> bool:  # type: ignore
        return dt.is_numeric()


def _get_uniform_text_min_size(config_params: dict, naming_params: dict) -> int:
    """Return the configured uniform text minimum size.

    Raises
    ------
    KeyError
        If the required key is missing from ``config_params``.
    """
    key = naming_params["uniformTextMinSize"]
    return config_params[key]


def _stacked_bar_category_column(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict
) -> str:
    """Return the categorical axis column for legacy stacked-bar plots."""

    namingParams = get_naming_params()
    xAxisDimensionKey = namingParams["xAxisDimension"]
    columns, schema = get_schema_and_column_names(df)
    configured = chartDict.get(xAxisDimensionKey)
    if configured in columns:
        return str(configured)
    if schema:
        for column in columns:
            dtype = schema.get(column)
            if dtype is not None and not is_numeric_dtype(dtype):
                return column
    if not columns:
        raise KeyError("Stacked bar data has no columns.")
    return columns[0]


def _stacked_bar_value_columns(
    df: pl.DataFrame | pl.LazyFrame, value_cols: list[str], chartDict: dict
) -> list[str]:
    """Return numeric stacked-bar trace columns, excluding the category axis."""

    namingParams = get_naming_params()
    valueName = namingParams["valueName"]
    category_col = _stacked_bar_category_column(df, chartDict)
    columns, schema = get_schema_and_column_names(df)
    candidate_cols = [
        column
        for column in value_cols
        if column in columns and column not in {category_col, valueName}
    ]
    if schema:
        numeric_cols = [
            column
            for column in candidate_cols
            if schema.get(column) is not None and is_numeric_dtype(schema[column])
        ]
    else:
        numeric_cols = candidate_cols
    if not numeric_cols and valueName in columns:
        numeric_cols = [valueName]
    return numeric_cols


def _should_hide_single_segment_stacked_column_text(
    df: pl.DataFrame | pl.LazyFrame,
    colname: str,
    naming_params: dict,
) -> bool:
    """Return True when a column chart has no stacked segments to label."""

    valueName = naming_params["valueName"]
    periodName = naming_params["periodName"]
    countName = naming_params["countName"]
    if colname == valueName:
        return True

    layout_cols = {periodName, valueName, countName, "x", "width_col", "halfColumn"}
    columns, schema = get_schema_and_column_names(df)
    segment_cols = [
        column
        for column in columns
        if column not in layout_cols
        and schema.get(column) is not None
        and is_numeric_dtype(schema[column])
    ]
    return len(segment_cols) <= 1


def _small_multiple_total_metric_column(
    df: pl.DataFrame | pl.LazyFrame, value_cols: list[str], chartDict: dict
) -> str | None:
    """Choose the plotted numeric metric used to order small-multiple panels."""

    naming = get_naming_params()
    columns, schema = get_schema_and_column_names(df)
    multiplied_metric = chartDict.get(naming["multipliedMetric"])
    if multiplied_metric in columns and schema.get(multiplied_metric) is not None:
        if is_numeric_dtype(schema[multiplied_metric]):
            return str(multiplied_metric)
    for column in value_cols:
        if column in columns and schema.get(column) is not None:
            if is_numeric_dtype(schema[column]):
                return column
    for column in columns:
        dtype = schema.get(column)
        if dtype is not None and is_numeric_dtype(dtype):
            return column
    return None


_SMALL_MULTIPLE_PREFIX_DIVISORS = (
    ("t", 1_000_000_000_000),
    ("b", 1_000_000_000),
    ("m", 1_000_000),
    ("k", 1_000),
    ("", 1),
)


def _shared_small_multiple_prefix(values: list[float]) -> str:
    """Choose one readable value prefix for all panels in a small multiple."""

    positive_values = [abs(float(value)) for value in values if value]
    if not positive_values:
        return ""
    smallest = min(positive_values)
    for prefix, divisor in _SMALL_MULTIPLE_PREFIX_DIVISORS:
        if divisor and smallest / divisor >= 0.05:
            return prefix
    return ""


def _pin_small_multiple_metric_prefixes(
    df: pl.DataFrame | pl.LazyFrame,
    facet_column: str,
    candidate_metrics: list[str | None],
    chartDict: dict,
) -> dict:
    """Keep Mekko small-multiple labels and titles on the same metric units."""

    naming = get_naming_params()
    columns, schema = get_schema_and_column_names(df)
    if facet_column not in columns:
        return chartDict

    metrics: list[str] = []
    seen: set[str] = set()
    for metric in candidate_metrics:
        if not metric or metric in seen or metric not in columns:
            continue
        dtype = schema.get(metric)
        if dtype is not None and not is_numeric_dtype(dtype):
            continue
        seen.add(metric)
        metrics.append(str(metric))
    if not metrics:
        return chartDict

    totals = (
        ensure_lazyframe(df)
        .group_by(facet_column)
        .agg([pl.col(metric).fill_null(0).sum().alias(metric) for metric in metrics])
        .collect(engine="streaming")
    )
    prefix_dict = chartDict.setdefault(naming["valuePrefixDict"], {})
    for metric in metrics:
        prefix_dict[metric] = _shared_small_multiple_prefix(
            totals.get_column(metric).to_list()
        )
    axis_metrics = {
        chartDict.get(naming["xAxisMetric"]),
        chartDict.get(naming["yAxisMetric"]),
    }
    alias_metrics = [
        chartDict.get(naming["multipliedMetric"]),
        naming["valueName"],
    ]
    area_sources = [
        metric
        for metric in metrics
        if metric not in axis_metrics and metric not in alias_metrics
    ]
    source_metric = area_sources[-1] if area_sources else metrics[-1]
    if source_metric:
        source_prefix = prefix_dict[source_metric]
        for alias_metric in alias_metrics:
            if alias_metric:
                prefix_dict[str(alias_metric)] = source_prefix
    return chartDict


def _category_first_stacked_bar_frame(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict
) -> pl.LazyFrame:
    """Keep the stacked-bar category axis as the first column.

    The legacy pandas implementation carried this axis in the index. The Polars
    port keeps it as a normal column, so downstream helpers that read the first
    column need it first.
    """

    category_col = _stacked_bar_category_column(df, chartDict)
    columns, _ = get_schema_and_column_names(df)
    return ensure_lazyframe(df).select(
        [category_col] + [column for column in columns if column != category_col]
    )


def stacked_bar_width_plot(
    df, chartDict, paramDict, value_cols, width_col, colors=None, **subplot
):
    """A stacked column plot with variable bar width.
    :param df
    :param list value_cols: columns of `df`, already normalized (sum=1 for every line).
    :param str width_col: column of `df`, unbounded, used (i) as label (ii) to compute width.
    :param dict subplot: optional figure/row/col
    """
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    chosenChart = namingParams["chosenChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    valueName = namingParams["valueName"]
    totalName = namingParams["totalName"]
    periodName = namingParams["periodName"]
    xAxisMetric = namingParams["xAxisMetric"]
    showValuesAs = namingParams["showValuesAs"]
    showLegend = namingParams["showLegend"]
    showBoth = namingParams["showBoth"]
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    showLegendOnTop = namingParams["showLegendOnTop"]
    showCAGR = namingParams["showCAGR"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    valueName = namingParams["valueName"]
    plName = namingParams["plName"]
    synthesisPlot = namingParams["synthesisPlot"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesDimension = namingParams["smallMultiplesDimension"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    chosenChart = chartDict[chosenChart]
    totalArea = None
    smallMultiples = False
    row, col = None, None
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        smallMultiples = True
    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        value_cols = [valueName]
    (
        totalXaxis,
        totalYaxis,
        dfNegative,
        message,
        totalXaxisNumber,
        totalYaxisNumber,
        totalAreaNumber,
    ) = (None, None, pl.DataFrame(), None, 0, 0, 0)
    if showValuesAs in chartDict:
        showValuesAs = chartDict[showValuesAs]
    if chosenChart in [stackedParetoChart]:
        df, dfDataColMetrics, dfCounts = split_main_and_data_column_dataframe(
            df, chartDict
        )
    if chosenChart in [barmekkoChart, marimekkoChart, stackedBarChart]:
        totalYaxis, totalYaxisNumber = get_y_axis_total(
            df, chartDict, value_cols, width_col
        )
        if chosenChart in [barmekkoChart]:
            df, dfNegative, message = check_if_negative_values_in_mekko(
                df, chartDict[xAxisMetric]
            )
            totalXaxis, totalArea, totalXaxisNumber, totalAreaNumber = get_x_axis_total(
                df, totalYaxisNumber, chartDict
            )
        elif chosenChart in [marimekkoChart]:
            df, dfNegative, message = check_if_negative_values_in_mekko(df, valueName)
    if chosenChart in [
        stackedParetoChart,
        stackedColumnChart,
        stackedBarChart,
        marimekkoChart,
    ]:
        dfCumSum, dfNegative, message = get_cum_sum_dataframe(
            df, chosenChart, dfNegative, message
        )

    df = modify_dataframe_for_Plan(df, chartDict)
    df = change_index_names_if_cost_analysis(df, chartDict)
    if chosenChart in [stackedBarChart]:
        df = _category_first_stacked_bar_frame(df, chartDict)
        value_cols = _stacked_bar_value_columns(df, value_cols, chartDict)
    categories, numberOfCols, colors, figure = prepare_arrays_to_add_traces(
        df, colors, value_cols, subplot, paramDict, chartDict
    )

    df, chartDict = add_blank_column_for_data_column_annotations(
        df, chosenChart, chartDict
    )
    count = 0
    xticktext, yticktext = ["     ", "     "], [
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
        "    ",
        "     ",
    ]
    halfColumn = False
    columns, schema = get_schema_and_column_names(df)
    for colname, color in zip(value_cols, colors):
        if chosenChart in [stackedParetoChart]:
            (
                figure,
                halfColumn,
                yticktext,
                tickformat,
                rangeArray,
                visible,
                showticklabels,
                tickvals,
                tickrange,
                barmode,
                bargap,
                maxLabelLength,
                chartDict,
            ) = set_stacked_pareto_params_and_add_trace(
                figure, subplot, df, dfCounts, colname, color, chartDict, categories
            )
        elif chosenChart in [stackedColumnChart] and (
            colname in [valueName] or colname in columns
        ):
            (
                figure,
                halfColumn,
                yticktext,
                tickformat,
                rangeArray,
                visible,
                showticklabels,
                tickvals,
                tickrange,
                barmode,
                bargap,
                maxLabelLength,
                chartDict,
            ) = set_stacked_column_params_and_add_trace(
                figure,
                subplot,
                df,
                colname,
                color,
                chartDict,
                categories,
                numberOfCols,
                count,
            )
        elif chosenChart in [stackedBarChart]:
            (
                figure,
                halfColumn,
                xticktext,
                tickformat,
                rangeArray,
                visible,
                showticklabels,
                tickvals,
                tickrange,
                barmode,
                bargap,
                chartDict,
                row,
                col,
                halfColumn_lazy,
            ) = set_stacked_bar_params_and_add_trace(
                figure,
                subplot,
                df,
                colname,
                color,
                width_col,
                chartDict,
                categories,
                numberOfCols,
            )
        elif chosenChart in [marimekkoChart]:
            (
                figure,
                halfColumn,
                xticktext,
                tickformat,
                rangeArray,
                visible,
                showticklabels,
                tickvals,
                tickrange,
                barmode,
                bargap,
                chartDict,
                row,
                col,
            ) = set_marimekko_params_and_add_trace(
                figure,
                subplot,
                ensure_polars_df(df),
                colname,
                color,
                width_col,
                chartDict,
                showValuesAs,
                categories,
            )
        elif chosenChart in [barmekkoChart]:
            (
                figure,
                halfColumn,
                xticktext,
                tickformat,
                rangeArray,
                visible,
                showticklabels,
                tickvals,
                tickrange,
                barmode,
                bargap,
                chartDict,
                row,
                col,
            ) = set_barmekko_params_and_add_trace(
                figure,
                subplot,
                df,
                colname,
                color,
                chartDict,
                showValuesAs,
                categories,
                paramDict,
            )
        if plotSmallMultiplesKey not in chartDict or not smallMultiples:
            row, col = None, None
        if chosenChart in [stackedParetoChart]:
            if chartDict[showLegend] in [showBoth, showLegendLeftOrRight]:
                figure = add_legends_on_left(
                    figure,
                    df,
                    dfCumSum,
                    numberOfCols,
                    value_cols,
                    colname,
                    count,
                    chartDict,
                )
                pass
            if (
                showMetricsInDataColumn in chartDict
                and chartDict[showMetricsInDataColumn]
            ):
                figure = add_values_to_data_column_on_right(
                    figure,
                    df,
                    dfDataColMetrics,
                    dfCumSum,
                    value_cols,
                    colname,
                    count,
                    chartDict,
                    categories,
                )
                pass
        if chosenChart in [stackedColumnChart]:
            if colname != totalName:
                if synthesisPlot in chartDict and chartDict[synthesisPlot]:
                    pass
                elif chartDict[showLegend] in [showBoth, showLegendLeftOrRight]:
                    figure = add_legends_on_left_or_right(
                        figure,
                        df,
                        dfCumSum,
                        numberOfCols,
                        value_cols,
                        colname,
                        count,
                        chartDict,
                    )
                    pass
                if synthesisPlot in chartDict and chartDict[synthesisPlot]:
                    chartDict[showCAGR] = notMetConditionValue
                elif showCAGR in chartDict and chartDict[showCAGR]:
                    figure = add_cxgr_on_right(
                        figure,
                        df,
                        dfCumSum,
                        colname,
                        numberOfCols,
                        value_cols,
                        count,
                        chartDict,
                    )
                    pass
            else:
                pass
                try:
                    figure, chartDict = add_overlay_trace(
                        figure, df, colors, chartDict, None, None
                    )
                except Exception as e:
                    logging.exception(e)
                    ui.error("Something went wrong while adding the overlay trace.")
                    e = print_error_details(e)
                    paramDict = add_app_message_to_paramdict(
                        e,
                        errorMessageType,
                        plotChartsTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=True,
                        colNumber=0,
                    )
        if chosenChart in [stackedBarChart, marimekkoChart]:
            if chartDict[showLegend] in [showBoth, showLegendOnTop]:
                if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
                    nothingFilteredName
                ]:
                    pass
                else:
                    pass
                    if (
                        plotSmallMultiplesKey in chartDict
                        and chartDict[plotSmallMultiplesKey]
                    ):
                        pass
                        figure = add_legends_on_top(
                            figure,
                            chosenChart,
                            df,
                            dfCumSum,
                            value_cols,
                            colname,
                            count,
                            chartDict,
                            row,
                            col,
                        )
                    else:
                        pass
                        if chosenChart != marimekkoChart:
                            figure = add_legends_on_top(
                                figure,
                                chosenChart,
                                df,
                                dfCumSum,
                                value_cols,
                                colname,
                                count,
                                chartDict,
                                row,
                                col,
                            )
                        if not (smallMultiples and chosenChart in [marimekkoChart]):
                            figure = add_totals_below(
                                figure,
                                chosenChart,
                                df,
                                dfCumSum,
                                value_cols,
                                colname,
                                count,
                                totalYaxisNumber,
                                chartDict,
                                row,
                                col,
                            )
        count = count + 1
    if chosenChart in [
        barmekkoChart,
        marimekkoChart,
        stackedParetoChart,
        stackedColumnChart,
    ]:
        if smallMultiples and chosenChart in [marimekkoChart, barmekkoChart]:
            columns, schema = get_schema_and_column_names(df)
            if valueName in columns:
                width = df.select([columns[0], valueName]).lazy()
                half_to_use = halfColumn
                if chosenChart == marimekkoChart:
                    half_to_use = calculate_marimekko_positions(
                        df, namingParams["countName"], valueName
                    ).select(pl.col(columns[0]), pl.col("halfColumn"))
                elif chosenChart == barmekkoChart and isinstance(half_to_use, list):
                    first_col = columns[0]
                    if len(half_to_use) == len(categories):
                        half_to_use = pl.DataFrame(
                            {first_col: categories, "halfColumn": half_to_use}
                        ).lazy()
                figure, chartDict = add_total_annotations(
                    figure,
                    chartDict,
                    categories,
                    half_to_use,
                    width,
                    df,
                    row,
                    col,
                )
            figure = add_first_row_annotations(
                df,
                figure,
                chartDict,
                totalYaxisNumber,
                totalXaxisNumber,
                totalAreaNumber,
                numberOfCols,
                count,
                row,
                col,
            )
            if chosenChart in [barmekkoChart]:
                figure.update_xaxes(showticklabels=True)
                figure.update_yaxes(showticklabels=True)
        elif (
            chosenChart in [stackedColumnChart]
            and synthesisPlot in chartDict
            and chartDict[synthesisPlot]
        ):
            figure = add_first_row_annotations(
                df,
                figure,
                chartDict,
                totalYaxisNumber,
                totalXaxisNumber,
                totalAreaNumber,
                numberOfCols,
                count,
                row,
                col,
            )
        elif not smallMultiples:
            columns, _ = get_schema_and_column_names(df)
            if valueName in columns:
                if periodName in columns:
                    selectCols = [periodName, valueName]
                else:
                    selectCols = [columns[0], valueName]
                width = df.select(selectCols).lazy()
                half_to_use = halfColumn
                if chosenChart == marimekkoChart:
                    half_to_use = calculate_marimekko_positions(
                        df, namingParams["countName"], valueName
                    ).select(pl.col(columns[0]), pl.col("halfColumn"))
                elif chosenChart == barmekkoChart and isinstance(half_to_use, list):
                    # ``set_barmekko_params_and_add_trace`` returns raw half-column values;
                    # convert to a lazy frame to match ``add_total_annotations`` expectations.
                    first_col = columns[0]
                    if len(half_to_use) == len(categories):
                        half_to_use = pl.DataFrame(
                            {first_col: categories, "halfColumn": half_to_use}
                        ).lazy()
                figure, chartDict = add_total_annotations(
                    figure,
                    chartDict,
                    categories,
                    half_to_use,
                    width,
                    df,
                    row,
                    col,
                )
            figure = add_first_row_annotations(
                df,
                figure,
                chartDict,
                totalYaxisNumber,
                totalXaxisNumber,
                totalAreaNumber,
                numberOfCols,
                count,
                row,
                col,
            )
    if chosenChart in [stackedBarChart]:
        columns, schema = get_schema_and_column_names(df)

        if valueName in columns:
            category_col = _stacked_bar_category_column(df, chartDict)
            width = df.select([category_col, valueName]).lazy()
            figure, chartDict = add_total_annotations(
                figure,
                chartDict,
                categories,
                halfColumn_lazy,
                width,
                df,
                row,
                col,
            )
        if 1 == 1 or not smallMultiples:
            pass
            figure = add_first_row_annotations(
                df,
                figure,
                chartDict,
                totalYaxisNumber,
                totalXaxisNumber,
                totalAreaNumber,
                numberOfCols,
                count,
                row,
                col,
            )
        figure, chartDict = add_overlay_trace(figure, df, colors, chartDict, row, col)
    yticktext = adjust_tick_text(yticktext, chosenChart, chartDict)
    if len(value_cols) > 0:
        if chosenChart in [marimekkoChart, barmekkoChart]:
            figure = update_yaxes_bar_width_plot_vertical(
                figure,
                tickvals,
                xticktext,
                tickformat,
                tickrange,
                visible,
                showticklabels,
                row,
                col,
            )
            pass
            figure = update_xaxes_bar_width_plot_vertical(
                figure, tickvals, yticktext, None, row, col, showticklabels
            )
        else:
            pass
            figure = update_yaxes_bar_width_plot_horizontal(
                figure,
                xticktext,
                tickformat,
                rangeArray,
                visible,
                showticklabels,
                subplot,
            )
            figure = update_xaxes_bar_width_plot_horizontal(
                figure, tickvals, yticktext, tickrange, subplot, chartDict
            )
        figure = update_layout_bar_width_plot(
            figure, df, chosenChart, numberOfCols, chartDict, paramDict, barmode, bargap
        )
    return figure, dfNegative, message, chartDict


def adjust_stacked_bar_plot(fig, df, key, metric, title, paramDict, chartDict):
    namingParams = get_naming_params()
    configParams = get_config_params()
    chosenChart = namingParams["chosenChart"]
    uniformTextMinSize = _get_uniform_text_min_size(configParams, namingParams)
    chosenChart = chartDict[chosenChart]
    fig = update_stacked_bar_layout(fig, chartDict)
    fig, message = get_user_message(
        fig, chosenChart, "_None", key, paramDict, chartDict, df, None, None
    )
    fig = add_message_as_annotation(
        fig, message, None, chosenChart, chartDict, paramDict
    )
    fig = add_title_as_annotation(fig, title, chosenChart, chartDict)
    fig = enable_draw_shapes(fig)
    return fig


def adjust_stacked_column_plot(fig, df, key, metric, title, paramDict, chartDict):
    namingParams = get_naming_params()
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    fig = update_stacked_column_layout(fig, metric)
    # fig,message=get_user_message(fig,chosenChart,"_None",key,paramDict,chartDict,df,None,None)
    # fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
    fig = add_title_as_annotation(fig, title, chosenChart, chartDict)
    fig = enable_draw_shapes(fig)
    return fig


def add_first_row_annotations_for_stacked_column(
    figure, chartDict, numberOfColumns, count, row, col
):
    namingParams = get_naming_params()
    CXGRMetric = namingParams["CXGRMetricName"]
    CXGRTotal = namingParams["CXGRTotal"]
    totalName = namingParams["totalName"]
    CXGRData = namingParams["CXGRData"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    positionLegends = namingParams["positionLegends"]
    legendsAtRight = namingParams["legendsAtRight"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        xShift = get_x_shift_for_data_column(numberOfColumns, chartDict, "title")
        cxgrValueTitle = ""
        if chartDict[CXGRMetric]:
            cxgrValueTitle = chartDict[CXGRMetric]
        else:
            cxgrValueTitle = "CXGR"
        if CXGRTotal in chartDict:
            if len(chartDict[CXGRTotal]) > 0:
                totalCxgrValue = chartDict[CXGRTotal][totalName][0]
                cxgrValueTitle = (
                    cxgrValueTitle + "<br>" + " " + str(totalCxgrValue) + "%"
                )
            else:
                cxgrValueTitle = ""
        elif CXGRData in chartDict:
            if CXGRTotal in chartDict and len(chartDict[CXGRTotal]) > 0:
                totalCxgrValue = chartDict[CXGRData][totalName][0]
                cxgrValueTitle = (
                    cxgrValueTitle + "<br>" + " " + str(totalCxgrValue) + "%"
                )
            else:
                cxgrValueTitle = ""
        if (
            count != 1
            and positionLegends in chartDict
            and chartDict[positionLegends] == legendsAtRight
        ):
            xShift = xShift + 80
        figure.add_annotation(
            text=cxgrValueTitle,
            showarrow=False,
            align="center",
            yshift=25,
            ay=1,
            y=1,
            yref="paper",
            ax=1,
            x=1,
            xref="paper",
            xshift=xShift,
            row=row,
            col=col,
        )
    return figure


def set_stacked_column_params_and_add_trace(
    figure,
    subplot,
    df: pl.LazyFrame,
    colname,
    color,
    chartDict,
    categories,
    numberOfCols,
    count,
):
    """
    Main function orchestrating the logic, now using Polars lazy transformations.
    """
    # Grab your config/param dictionaries
    configParams = get_config_params()
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()

    # Extract arrays from metricArrayParams if needed
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]

    # Common naming
    countName = namingParams["countName"]
    labelName = namingParams["labelName"]
    stackedColumnMetric = namingParams["stackedColumnMetric"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    periodName = namingParams["periodName"]
    plName = namingParams["plName"]
    markerColorKey = namingParams["markerColor"]
    markerLineColorKey = namingParams["markerLineColor"]
    textFontColorKey = namingParams["textFontColor"]
    showLegend = namingParams["showLegend"]
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    rowName = namingParams["rowName"]
    columnName = namingParams["columnName"]
    hide_trace_text = _should_hide_single_segment_stacked_column_text(
        df,
        colname,
        namingParams,
    )

    # Decide how wide or offset bars should be
    bargap, offset, makeColsThin = set_bar_gap_offset(
        chartDict, namingParams, configParams, noSumMetricsArray
    )
    # row/col for subplot (if any)
    row, col, setColAndRow = 1, 1, False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if rowName in chartDict and chartDict[rowName]:
            row = chartDict[rowName]
            if columnName in chartDict and chartDict[columnName]:
                col = chartDict[columnName]
                setColAndRow = True

    # Prepare new columns: count=1, cumsum x, halfColumn, width_col
    df = compute_positions(df, countName, bargap, makeColsThin)

    # Possibly call your millify_dataframe function in a lazy manner
    # For illustration, we assume it just returns (df, chartDict) but is Polars-lazy safe
    df, chartDict = millify_dataframe(df, colname, None, labelName, chartDict)
    # Apply marker styles
    df = apply_marker_styles(df, chartDict, namingParams, color, count)

    # Decide text position, text color, etc. (pure Python logic)
    textposition = "auto"
    textfontcolor = "white"
    insidetextanchor = "middle"
    cliponaxis = False
    orientation = "v"
    barmode = "relative"

    # If you have logic about maxLabelLength:
    if numberOfCols <= 2:
        maxLabelLength = 40
    elif numberOfCols <= 5:
        maxLabelLength = 35
    elif numberOfCols <= 8:
        maxLabelLength = 15
    else:
        maxLabelLength = 10

    if chartDict.get(showLegend) != showLegendLeftOrRight:
        df = df.with_columns(
            (
                pl.lit(colname[:maxLabelLength] + " ") + pl.col(labelName).cast(pl.Utf8)
            ).alias(labelName)
        )

    # Collect once and extract required columns
    collected_df = df.select(
        [
            pl.col("x"),
            pl.col(colname),
            pl.col("width_col"),
            pl.col(labelName),
            pl.col(markerColorKey),
            pl.col(markerLineColorKey),
            pl.col(textFontColorKey),
            pl.col(countName),
        ]
    ).collect(engine="streaming")

    x = collected_df["x"].to_list()
    check_collect("AIA", "x", x)
    y = collected_df[colname].to_list()
    check_collect("ALA", "y", y)
    width = collected_df["width_col"].to_list()
    check_collect("AMA", "width", width)
    text_vals = collected_df[labelName].to_list()
    if hide_trace_text:
        text_vals = [""] * len(text_vals)
    check_collect("ANA", "text_vals", text_vals)
    marker_color_vals = collected_df[markerColorKey].to_list()
    check_collect("AOA", "marker_color_vals", marker_color_vals)
    marker_line_color_vals = collected_df[markerLineColorKey].to_list()
    check_collect("APA", "marker_line_color_vals", marker_line_color_vals)
    text_font_color_vals = collected_df[textFontColorKey].to_list()
    check_collect("AQA", "text_font_color_vals", text_font_color_vals)

    count_list = collected_df[countName].to_list()
    check_collect("ARA", "count_list", count_list)
    tickvals = []
    for xi, wi in zip(x, width):
        try:
            tickvals.append(xi + offset + wi / 2.0)
        except TypeError:
            tickvals.append(xi)

    # Plotly applies explicit bar offsets from the x position; use the rendered
    # column center for axis labels and total annotations.
    if isinstance(df, pl.DataFrame):
        columns, _ = get_schema_and_column_names(df)
    else:
        columns = df.collect_schema().names()
    label_col = periodName if periodName in columns else columns[0]
    halfColumn = ensure_lazyframe(df).select(
        pl.col(label_col),
        (pl.col("x") + pl.lit(offset) + pl.col("width_col") / 2.0).alias("halfColumn"),
    )
    check_collect("ASA", "halfColumn", halfColumn)

    # Build the trace (Plotly needs actual Python lists, hence the `.collect()` above)
    bar_trace = go.Bar(
        name=colname,
        x=x,
        y=y,
        width=width,
        marker_color=marker_color_vals,
        marker_line_color=marker_line_color_vals,
        text=text_vals,
        textposition=textposition,
        insidetextanchor=insidetextanchor,
        textfont_color=text_font_color_vals,
        offset=offset,
        orientation=orientation,
        cliponaxis=cliponaxis,
    )

    if setColAndRow:
        figure.add_trace(bar_trace, row=row, col=col)
    else:
        figure.add_trace(bar_trace, **subplot)

    # Just placeholders for final return. Adjust as needed.
    ticktext = categories  # or anything else
    tickformat = ""
    rangeArray = None
    visible = False
    showticklabels = False
    tickrange = [0, sum(count_list)]

    # Return figure and any relevant variables
    return (
        figure,
        halfColumn,
        ticktext,
        tickformat,
        rangeArray,
        visible,
        showticklabels,
        tickvals,
        tickrange,
        barmode,
        bargap,
        maxLabelLength,
        chartDict,
    )


def draw_stacked_column_chart(
    dfCopy,
    chosenDimension,
    xColumn,
    metricArray,
    repeatArray,
    paramDict,
    chartDict,
    uniqueItems,
    aggregateOtherItemsName,
    fullFig,
    metricType,
    columnsToPlot,
):
    """
    draw chart
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    labelName = namingParams["labelName"]
    chosenChart = namingParams["chosenChart"]
    totalName = namingParams["totalName"]
    numberOfPlots = namingParams["numberOfPlots"]
    plName = namingParams["plName"]
    pyName = namingParams["pyName"]
    acName = namingParams["acName"]
    periodName = namingParams["periodName"]
    stackedColumnMetric = namingParams["stackedColumnMetric"]
    configPlotlyDict = configParams["configPlotlyDict"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    rowName = namingParams["rowName"]
    columnName = namingParams["columnName"]
    fixedScaleChoice = namingParams["fixedScaleChoice"]
    overlayChartDfKey = namingParams["overlayChartDf"]
    chosenChart = chartDict[chosenChart]
    configPlotlyDict = configPlotlyDict[chosenChart]
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)
    if len(uniqueItems) > 1:
        colorArray = set_other_color_to_grey(
            uniqueItems, aggregateOtherItemsName, colorArray, chartDict, 0
        )
    df = duplicate_dataframe(dfCopy)
    key = None
    if is_valid_lazyframe(df):
        repeatArrayToPlot = []
        for element in repeatArray:
            repeatArrayToPlot.append(element)
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            paramDict, numberOfCols, numberOfRows = setup_fig_for_stacked_column_charts(
                df, repeatArrayToPlot, chosenDimension, paramDict, chartDict
            )
            chartDict[rowName], chartDict[columnName] = 1, 1
        count, countRows, countCols = 1, 1, 1
        columns, schema = get_schema_and_column_names(df)
        axis = "Y"
        if chosenDimension in columns and chosenDimension != totalName:
            if (
                plotSmallMultiplesKey not in chartDict
                or not chartDict[plotSmallMultiplesKey]
            ):
                paramDict, numberOfCols, numberOfRows = (
                    setup_fig_for_stacked_column_charts(
                        df, repeatArrayToPlot, chosenDimension, paramDict, chartDict
                    )
                )
                for metric in metricArray:
                    chartDict[stackedColumnMetric] = metric
                    df1 = duplicate_dataframe(df)
                    (
                        df1,
                        columns,
                        colorArray,
                        chartDict,
                        leastRecentPeriod,
                        mostRecentPeriod,
                    ) = prepare_data_for_stacked_column(
                        df1,
                        metric,
                        chosenDimension,
                        xColumn,
                        aggregateOtherItemsName,
                        chartDict,
                        paramDict,
                    )
                    fig, dfNegative, message, chartDict = stacked_bar_width_plot(
                        df1,
                        chartDict,
                        paramDict,
                        columns,
                        width_col=None,
                        colors=colorArray,
                    )
                    if metric == metricArray[0]:
                        fig, paramDict = get_chart_scale(
                            fig,
                            chartDict,
                            paramDict,
                            axis,
                            metric + chosenDimension,
                            chosenChart,
                            fixedScaleChoice,
                        )
                    fig, fullFig, metricType = keep_same_scale_for_all_plots(
                        fig, metric, metricType, fullFig, axis
                    )
                    key = chosenDimension
                    titleColumn = chosenDimension
                    title, paramDict, chartDict = make_stacked_column_chart_title(
                        df1,
                        chosenChart,
                        paramDict,
                        chosenDimension,
                        metric,
                        chartDict,
                        leastRecentPeriod,
                        mostRecentPeriod,
                    )
                    if len(columnsToPlot) <= 2:
                        fig = adjust_stacked_column_plot(
                            fig, df1, key, metric, title, paramDict, chartDict
                        )
                        paramDict = set_up_tab_for_show_or_download_chart(
                            df1,
                            fig,
                            configPlotlyDict,
                            chartDict,
                            chosenDimension + metric,
                            False,
                            None,
                            chosenDimension,
                            paramDict,
                        )
            else:
                for column in repeatArrayToPlot:
                    chartDict[stackedColumnMetric] = metricArray[0]
                    df1 = duplicate_dataframe(df)
                    maxValue = _column_max_value(df1, metricArray[0])
                    prefix, chartDict, decimals = get_number_prefix(
                        maxValue, chartDict, None, False
                    )
                    df1 = df1.filter(pl.col(chosenDimension) == column)
                    (
                        df1,
                        columns,
                        colorArray,
                        chartDict,
                        leastRecentPeriod,
                        mostRecentPeriod,
                    ) = prepare_data_for_stacked_column(
                        df1,
                        metricArray[0],
                        chosenDimension,
                        xColumn,
                        aggregateOtherItemsName,
                        chartDict,
                        paramDict,
                    )
                    fig, dfNegative, message, chartDict = stacked_bar_width_plot(
                        df1,
                        chartDict,
                        paramDict,
                        columns,
                        width_col=None,
                        colors=colorArray,
                    )
                    count, countRows, countCols, chartDict = (
                        reset_row_and_column_counters(
                            count,
                            countCols,
                            countRows,
                            numberOfCols,
                            numberOfRows,
                            chartDict,
                        )
                    )
        else:
            paramDict[numberOfPlots] = len(metricArray)
            countMetric = 0
            for metric in metricArray:
                if countMetric == 0 or overlayChartDfKey not in chartDict:
                    chartDict[stackedColumnMetric] = metric
                    df1 = duplicate_dataframe(df)
                    if (
                        plotSmallMultiplesKey not in chartDict
                        or not chartDict[plotSmallMultiplesKey]
                    ):
                        paramDict, numberOfCols, numberOfRows = (
                            setup_fig_for_stacked_column_charts(
                                df1,
                                repeatArrayToPlot,
                                chosenDimension,
                                paramDict,
                                chartDict,
                            )
                        )
                    (
                        df1,
                        columns,
                        colorArray,
                        chartDict,
                        leastRecentPeriod,
                        mostRecentPeriod,
                    ) = prepare_data_for_stacked_column(
                        df1,
                        metric,
                        chosenDimension,
                        xColumn,
                        aggregateOtherItemsName,
                        chartDict,
                        paramDict,
                    )
                    fig, dfNegative, message, chartDict = stacked_bar_width_plot(
                        df1,
                        chartDict,
                        paramDict,
                        columns,
                        width_col=None,
                        colors=colorArray,
                    )
                    if metric == metricArray[0]:
                        fig, paramDict = get_chart_scale(
                            fig,
                            chartDict,
                            paramDict,
                            axis,
                            metric + chosenDimension,
                            chosenChart,
                            fixedScaleChoice,
                        )
                    count, countRows, countCols, chartDict = (
                        reset_row_and_column_counters(
                            count,
                            countCols,
                            countRows,
                            numberOfCols,
                            numberOfRows,
                            chartDict,
                        )
                    )
                    key = chosenDimension + metric
                    if (
                        plotSmallMultiplesKey not in chartDict
                        or not chartDict[plotSmallMultiplesKey]
                    ):
                        title, paramDict, chartDict = make_stacked_column_chart_title(
                            df1,
                            chosenChart,
                            paramDict,
                            chosenDimension,
                            metric,
                            chartDict,
                            leastRecentPeriod,
                            mostRecentPeriod,
                        )
                        fig = adjust_stacked_column_plot(
                            fig, df1, key, metric, title, paramDict, chartDict
                        )
                        paramDict = set_up_tab_for_show_or_download_chart(
                            df1,
                            fig,
                            configPlotlyDict,
                            chartDict,
                            chosenDimension + metric,
                            False,
                            None,
                            chosenDimension,
                            paramDict,
                        )
                        countMetric = countMetric + 1
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            key = chosenDimension
            title, paramDict, chartDict = make_stacked_column_chart_title(
                df,
                chosenChart,
                paramDict,
                chosenDimension,
                metricArray[0],
                chartDict,
                leastRecentPeriod,
                mostRecentPeriod,
            )
            fig = adjust_stacked_column_plot(
                fig, df, key, metricArray[0], title, paramDict, chartDict
            )
            paramDict = set_up_tab_for_show_or_download_chart(
                df,
                fig,
                configPlotlyDict,
                chartDict,
                chosenDimension + metricArray[0],
                False,
                None,
                chosenDimension,
                paramDict,
            )
    else:
        paramDict = add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return fullFig, metricType, df1, chartDict, paramDict


def set_stacked_bar_params_and_add_trace(
    figure: go.Figure,
    subplot: dict,
    df: pl.DataFrame | pl.LazyFrame,
    colname: str,
    color: str,
    width_col: str | None,
    chartDict: dict,
    categories: list[str],
    numberOfCols: int,
) -> tuple:
    """Add a stacked bar trace keeping ``df`` lazy until plotting.

    The dataframe remains a ``LazyFrame`` throughout all transformations and is
    collected exactly once right before converting columns to Python lists for
    Plotly. Limits for the number of periods displayed are read directly from
    the configuration.
    """

    configParams = get_config_params()
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    max_period_key = namingParams["maxPeriodsForLabels"]
    bar_period_key = namingParams["maxPeriodsForBarChart"]
    maxPeriodsForLabels = configParams[max_period_key]
    maxPeriodsForBarChart = configParams[bar_period_key]
    countName = namingParams["countName"]
    totalName = namingParams["totalName"]
    labelName = namingParams["labelName"]
    valueName = namingParams["valueName"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    showLegend = namingParams["showLegend"]
    showBoth = namingParams["showBoth"]
    showLegendOnTop = namingParams["showLegendOnTop"]
    showLegendInBars = namingParams["showLegendInBars"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    metricsToPlot = namingParams["metricsToPlot"]
    stackedColumnMetric = namingParams["stackedColumnMetric"]
    rowNameKey = namingParams["rowName"]
    columnNameKey = namingParams["columnName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    defaultAverageShownArray = (
        priceMetricsArray + percentMetricsArray + growthMetricArray
    )
    periodName = namingParams["periodName"]
    orientation = "h"
    if metricsToPlot in chartDict and len(chartDict[metricsToPlot]) > 0:
        chartDict[stackedColumnMetric] = chartDict[metricsToPlot][0]
    bargap = 0.1
    if (
        metricsToPlot in chartDict
        and len(chartDict[metricsToPlot]) > 0
        and chartDict[metricsToPlot][0] in defaultAverageShownArray
    ):
        bargap = 0.25
    lf = compute_positions(ensure_lazyframe(df), countName, bargap, False)
    label_col = _stacked_bar_category_column(lf, chartDict)
    halfColumn_lazy = compute_half_column(lf, label_col)

    maxLabelLength = 60
    textposition = "auto"
    textfontcolor = "white"
    insidetextanchor = "middle"
    numberOfCols = len(categories)
    texttemplate = None
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        pass
        # chartDict[showLegend]=showLegendInBars
    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] == absolute:
        texttemplate, textformat = get_text_template(chartDict)
    if chartDict[plotValuesAsChoice] != absolute:
        lf, chartDict = millify_dataframe(lf, valueName, colname, labelName, chartDict)
        if chartDict[showLegend] in [showBoth, showLegendInBars]:
            lf = lf.with_columns(
                (
                    pl.lit(colname[:maxLabelLength] + " ")
                    + pl.col(labelName).cast(pl.Utf8)
                ).alias(labelName)
            )
    elif chartDict[showLegend] in [showBoth, showLegendInBars]:
        lf, chartDict = millify_dataframe(lf, valueName, colname, labelName, chartDict)
        lf = lf.with_columns(
            (
                pl.lit(colname[:maxLabelLength] + " ") + pl.col(labelName).cast(pl.Utf8)
            ).alias(labelName)
        )
        texttemplate = None
    else:
        lf, chartDict = millify_dataframe(lf, valueName, colname, labelName, chartDict)

    collected = lf.select(
        [
            pl.col(label_col).cast(pl.Utf8).alias("__category"),
            pl.col("x"),
            pl.col("halfColumn"),
            pl.col("width_col"),
            pl.col(countName),
            pl.col(colname),
            pl.col(labelName),
        ]
    ).collect(engine="streaming")
    width = collected["width_col"].to_list()
    x = collected["x"].to_list()
    halfColumn = collected["halfColumn"].to_list()
    y_values = collected["__category"].to_list()
    count_vals = collected[countName].to_list()
    text = collected[labelName].to_list()
    x_vals = collected[colname].to_list()
    trace_y = y_values if len(y_values) == len(x_vals) else categories
    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        text = None
        texttemplate = None
    row, col, setColAndRow = 1, 1, False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if rowNameKey in chartDict and chartDict[rowNameKey]:
            row = chartDict[rowNameKey]
            if columnNameKey in chartDict and chartDict[columnNameKey]:
                col = chartDict[columnNameKey]
                setColAndRow = True

    tickformat = ""
    rangeArray = None
    visible = True
    showticklabels = True
    barmode = "relative"
    tickvals = [xi + cv / 2 for xi, cv in zip(x, count_vals)]
    ticktext = [str(c) for c in categories]
    tickrange = None
    if setColAndRow:
        figure.add_trace(
            go.Bar(
                name=colname,
                x=x_vals,
                y=trace_y,
                width=width,
                marker_color=color,
                text=text,
                texttemplate=texttemplate,
                textposition=textposition,
                textangle=0,
                textfont_color=textfontcolor,
                insidetextanchor=insidetextanchor,
                hovertemplate=texttemplate,
                hovertext=text,
                offset=-0.45,
                orientation=orientation,
            ),
            row=row,
            col=col,
        )
    else:
        figure.add_trace(
            go.Bar(
                name=colname,
                x=x_vals,
                y=trace_y,
                width=width,
                marker_color=color,
                text=text,
                texttemplate=texttemplate,
                textposition=textposition,
                textangle=0,
                textfont_color=textfontcolor,
                insidetextanchor=insidetextanchor,
                hovertemplate=texttemplate,
                hovertext=text,
                offset=-0.45,
                orientation=orientation,
            ),
            **subplot,
        )
    return (
        figure,
        halfColumn,
        ticktext,
        tickformat,
        rangeArray,
        visible,
        showticklabels,
        tickvals,
        tickrange,
        barmode,
        bargap,
        chartDict,
        row,
        col,
        halfColumn_lazy,
    )


def prepare_small_multiple_mekko_df(
    df: pl.DataFrame | pl.LazyFrame,
    dimension: str,
    second_dimension_items: list[str],
    small_multiples_column: str,
    value_cols: list[str],
    chartDict: dict,
    paramDict: dict,
    usedColorDict: dict,
    xColumn: str,
    global_unique_items: list[str],
) -> tuple[
    pl.LazyFrame,
    str,
    list[str],
    dict,
    dict,
    str,
]:
    """Return a LazyFrame for one Mekko small multiple.

    LazyFrame inputs are collected with ``engine="streaming"`` for memory efficiency.
    """

    naming = get_naming_params()
    xAxisDimensionKey = naming["xAxisDimension"]
    fatherAndChildDimensions = naming["fatherAndChildDimensions"]
    globalUniqueItemsArrayKey = naming["globalUniqueItemsArray"]

    lf = ensure_lazyframe(df)
    lf = ensure_lazyframe(
        filter_small_multiples_dataframe(
            lf, dimension, second_dimension_items, small_multiples_column
        )
    )

    if fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]:
        lf, _items, _agg, value_cols = show_only_largest(
            lf,
            chartDict[xAxisDimensionKey],
            None,
            xColumn,
            value_cols,
            chartDict,
            paramDict,
            "X",
        )
        lf = ensure_lazyframe(lf)
    else:
        paramDict[globalUniqueItemsArrayKey] = global_unique_items

    (
        df_filtered,
        metric_to_plot,
        colorArray,
        usedColorDict,
        chartDict,
        period,
        _,
    ) = prepare_data_for_width_plot(
        lf, None, value_cols, chartDict, paramDict, usedColorDict
    )

    lf_filtered = ensure_lazyframe(df_filtered)

    lf_plot: pl.LazyFrame = lf_filtered.with_columns(
        pl.lit(dimension).alias(small_multiples_column)
    )
    return lf_plot, metric_to_plot, colorArray, usedColorDict, chartDict, period


def draw_stacked_bar_total(
    df, column, period, valueCols, chartDict, paramDict, usedColorDict
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    configPlotlyDict = configParams["configPlotlyDict"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    secondDimensionItemsArrayKey = namingParams["secondDimensionItemsArray"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    absolute = namingParams["absolute"]
    valueName = namingParams["valueName"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    chosenChartKey = namingParams["chosenChart"]
    xAxisDimensionKey = namingParams["xAxisDimension"]
    yAxisDimensionKey = namingParams["yAxisDimension"]
    chosenChart = chartDict[chosenChartKey]
    paramDict[globalUniqueItemsArrayKey] = None
    paramDict[secondDimensionItemsArrayKey] = []
    chartDict[plotSmallMultiplesKey] = notMetConditionValue
    (
        dfFiltered,
        metricToPlot,
        colorArray,
        usedColorDict,
        chartDict,
        column,
        uniqueItems,
    ) = prepare_data_for_width_plot(
        df, column, valueCols, chartDict, paramDict, usedColorDict
    )
    dfFiltered = ensure_lazyframe(dfFiltered)
    dfAbsolute = duplicate_dataframe(dfFiltered)
    chartDict[absolute] = dfAbsolute
    xAxisDimension = chartDict[xAxisDimensionKey]
    yAxisDimension = chartDict[yAxisDimensionKey]
    configPlotlyDict = configPlotlyDict[chosenChart]
    if get_row_count(dfFiltered) > 0:
        columns, schema = get_schema_and_column_names(dfFiltered)
        if valueName in columns:
            columns.remove(valueName)
            columns = _stacked_bar_value_columns(dfFiltered, columns, chartDict)
            if (
                plotValuesAsChoice in chartDict
                and chartDict[plotValuesAsChoice] != absolute
            ):
                dfFiltered = percentage_cols_lazy(dfFiltered, columns, valueName)
        fig, dfNegative, message, chartDict = stacked_bar_width_plot(
            dfFiltered, chartDict, paramDict, columns, width_col=None, colors=colorArray
        )
        if (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] == absolute
        ):
            title, paramDict, chartDict = make_marimekko_and_stacked_bar_chart_title(
                dfFiltered,
                chosenChart,
                paramDict,
                xAxisDimension,
                metricToPlot,
                chartDict,
                period,
                yAxisDimension,
            )
        else:
            title, paramDict, chartDict = make_marimekko_and_stacked_bar_chart_title(
                dfFiltered,
                chosenChart,
                paramDict,
                xAxisDimension,
                "% of " + metricToPlot,
                chartDict,
                period,
                yAxisDimension,
            )
            fig = show_total_percent(
                fig, df, dfFiltered, period, metricToPlot, chartDict
            )
        key = metricToPlot + period + column
        fig = adjust_stacked_bar_plot(
            fig, df, key, metricToPlot, title, paramDict, chartDict
        )
        paramDict = set_up_tab_for_show_or_download_chart(
            dfFiltered,
            fig,
            configPlotlyDict,
            chartDict,
            metricToPlot + period + xAxisDimension,
            False,
            None,
            xAxisDimension,
            paramDict,
        )
    return paramDict, usedColorDict


def draw_stacked_bar_chart(
    df,
    column,
    period,
    indexCols,
    valueCols,
    chartDict,
    paramDict,
    usedColorDict,
    xColumn,
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    if column == totalName:
        paramDict, usedColorDict = draw_stacked_bar_total(
            df, column, period, valueCols, chartDict, paramDict, usedColorDict
        )
    elif column != totalName:
        paramDict, usedColorDict, chartDict = draw_stacked_bar_small_multiples(
            df, column, period, valueCols, chartDict, paramDict, xColumn, usedColorDict
        )
    return usedColorDict, paramDict, chartDict


def find_scaling_factor_for_overlay_metric(
    df,
    column,
    valueCols,
    globalUniqueItems,
    xColumn,
    chartDict,
    paramDict,
    usedColorDict,
    count,
):
    namingParams = get_naming_params()
    metricsToPlot = namingParams["metricsToPlot"]
    secondDimensionItemsArrayKey = namingParams["secondDimensionItemsArray"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    xAxisDimensionKey = namingParams["xAxisDimension"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    globalAggregateKey = namingParams["globalAggregateKey"]
    smallMultiplesDimensionKey = namingParams["smallMultiplesDimension"]
    overlayChartFullDfKey = namingParams["overlayChartFullDf"]
    overlayChartDfKey = namingParams["overlayChartDf"]
    smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    xAxisDimension = chartDict[xAxisDimensionKey]
    globalAggregateOtherItems = paramDict[globalAggregateKey]
    frameArray = []
    fatherAndChildItems = []
    if count == 1 and metricsToPlot in chartDict and len(chartDict[metricsToPlot]) == 2:
        secondDimensionItems = paramDict[secondDimensionItemsArrayKey]
        for smallMultiplesDimension in secondDimensionItems:
            chartDict[smallMultiplesDimensionKey] = smallMultiplesDimension
            df1 = duplicate_dataframe(df)
            df1 = filter_small_multiples_dataframe(
                df1, smallMultiplesDimension, secondDimensionItems, smallMultiplesColumn
            )

            if (
                fatherAndChildDimensions in chartDict
                and chartDict[fatherAndChildDimensions]
            ) or chartDict[showTopForEachItem]:
                dfDump, fatherAndChildItems, globalAggregateOtherItems, valueCols = (
                    show_only_largest(
                        df1,
                        xAxisDimension,
                        None,
                        xColumn,
                        valueCols,
                        chartDict,
                        paramDict,
                        "X",
                    )
                )
            else:
                paramDict[globalUniqueItemsArrayKey] = globalUniqueItems
            df1, chartDict, colorArray, metricToPlot, frameArray = (
                prepare_small_multiples_dataframe_for_stacked_bar(
                    df1,
                    column,
                    valueCols,
                    chartDict,
                    paramDict,
                    usedColorDict,
                    globalUniqueItems,
                    fatherAndChildItems,
                    globalAggregateOtherItems,
                    smallMultiplesDimension,
                    frameArray,
                )
            )
        dfExport = pl.concat(frameArray, how="diagonal")
        overlayChartFullDf = chartDict[overlayChartFullDfKey]
        dfExport = dfExport.join(
            overlayChartFullDf,
            on=[smallMultiplesColumn, xAxisDimension],
            how="left",
        )
        chartDict = get_scaling_factor(dfExport, chartDict)
    return chartDict


def draw_stacked_bar_small_multiples(
    df, column, period, valueCols, chartDict, paramDict, xColumn, usedColorDict
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    configPlotlyDict = configParams["configPlotlyDict"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    xAxisDimensionKey = namingParams["xAxisDimension"]
    yAxisDimensionKey = namingParams["yAxisDimension"]
    secondDimensionItemsArrayKey = namingParams["secondDimensionItemsArray"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    globalAggregateKey = namingParams["globalAggregateKey"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    rowName = namingParams["rowName"]
    columnName = namingParams["columnName"]
    singleMetricKey = namingParams["singleMetric"]
    metricsToPlot = namingParams["metricsToPlot"]
    absolute = namingParams["absolute"]
    valueName = namingParams["valueName"]
    smallMultiplesDimensionKey = namingParams["smallMultiplesDimension"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    chosenChartKey = namingParams["chosenChart"]
    valuePrefixDict = namingParams["valuePrefixDict"]
    xAxisDimension = chartDict[xAxisDimensionKey]
    yAxisDimension = chartDict[yAxisDimensionKey]
    chosenChart = chartDict[chosenChartKey]
    chartDict[plotSmallMultiplesKey] = metConditionValue
    configPlotlyDict = configPlotlyDict[chosenChart]
    smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    dfPanelScope, secondDimensionItems, aggregateOtherItemsName, valueCols = (
        show_only_largest(
            df, column, xAxisDimension, xColumn, valueCols, chartDict, paramDict, "Y"
        )
    )
    orderMetric = _small_multiple_total_metric_column(
        dfPanelScope, valueCols, chartDict
    )
    if orderMetric:
        secondDimensionItems = order_small_multiple_facets_by_total(
            ensure_lazyframe(dfPanelScope),
            column,
            orderMetric,
            secondDimensionItems,
            aggregateOtherItemsName,
        )
    dfDump, globalUniqueItems, globalAggregateOtherItems, valueCols = show_only_largest(
        df, xAxisDimension, None, xColumn, valueCols, chartDict, paramDict, "X"
    )
    count, countRows, countCols = 1, 1, 1
    paramDict[secondDimensionItemsArrayKey] = secondDimensionItems
    paramDict[globalUniqueItemsArrayKey] = globalUniqueItems
    paramDict[globalAggregateKey] = globalAggregateOtherItems
    paramDict, numberOfCols, numberOfRows = setup_fig_for_stacked_bar_charts(
        df, column, secondDimensionItems, xAxisDimension, paramDict, chartDict
    )
    frameArray = []
    fatherAndChildItems = []
    checkDict = {}
    chartDict[rowName], chartDict[columnName] = 1, 1
    if len(secondDimensionItems) > 1:
        chartDict[numberOfPlottedSmallMultiplesKey] = len(secondDimensionItems)
        for smallMultiplesDimension in secondDimensionItems:
            chartDict = find_scaling_factor_for_overlay_metric(
                df,
                column,
                valueCols,
                globalUniqueItems,
                xColumn,
                chartDict,
                paramDict,
                usedColorDict,
                count,
            )
            singleMetric = chartDict[metricsToPlot][0]
            chartDict[smallMultiplesDimensionKey] = smallMultiplesDimension
            df1 = duplicate_dataframe(df)
            df1 = filter_small_multiples_dataframe(
                df1, smallMultiplesDimension, secondDimensionItems, smallMultiplesColumn
            )
            if (
                fatherAndChildDimensions in chartDict
                and chartDict[fatherAndChildDimensions]
            ) or chartDict[showTopForEachItem]:
                dfDump, fatherAndChildItems, globalAggregateOtherItems, valueCols = (
                    show_only_largest(
                        df1,
                        xAxisDimension,
                        None,
                        xColumn,
                        valueCols,
                        chartDict,
                        paramDict,
                        "X",
                    )
                )
            else:
                paramDict[globalUniqueItemsArrayKey] = globalUniqueItems
            if get_row_count(df1) > 0:
                df1, chartDict, colorArray, metricToPlot, frameArray = (
                    prepare_small_multiples_dataframe_for_stacked_bar(
                        df1,
                        column,
                        valueCols,
                        chartDict,
                        paramDict,
                        usedColorDict,
                        globalUniqueItems,
                        fatherAndChildItems,
                        globalAggregateOtherItems,
                        smallMultiplesDimension,
                        frameArray,
                    )
                )
                columns, schema = get_schema_and_column_names(df1)
                if valueName in columns:
                    columns.remove(valueName)
                    columns = _stacked_bar_value_columns(df1, columns, chartDict)
                    if (
                        plotValuesAsChoice in chartDict
                        and chartDict[plotValuesAsChoice] != absolute
                    ):
                        df1 = ensure_lazyframe(df1).with_columns(
                            [
                                (pl.col(c) / pl.col(valueName) * 100).alias(c)
                                for c in columns
                            ]
                        )
                df1 = drop_all_null_rows_lazy(ensure_lazyframe(df1))
                if valuePrefixDict in chartDict:
                    checkDict = chartDict[valuePrefixDict]
                fig, dfNegative, message, chartDict = stacked_bar_width_plot(
                    df1,
                    chartDict,
                    paramDict,
                    columns,
                    width_col=None,
                    colors=colorArray,
                )
                if len(checkDict) > 0:
                    chartDict[valuePrefixDict] = checkDict
                count, countRows, countCols, chartDict = reset_row_and_column_counters(
                    count, countCols, countRows, numberOfCols, numberOfRows, chartDict
                )
        fig = move_labels_up(fig, chartDict, secondDimensionItems)
        key = xAxisDimension
        title, paramDict, chartDict = make_marimekko_and_stacked_bar_chart_title(
            df1,
            chosenChart,
            paramDict,
            xAxisDimension,
            metricToPlot,
            chartDict,
            period,
            yAxisDimension,
        )
        key = metricToPlot + period + column
        fig = reset_height(
            fig, frameArray, chosenChart, numberOfCols, chartDict, paramDict
        )
        fig = adjust_stacked_bar_plot(
            fig, df, key, metricToPlot, title, paramDict, chartDict
        )
        if len(frameArray) > 0:
            dfExport = pl.concat(frameArray, how="diagonal")
            check_small_multiples_total(dfExport, df, metricToPlot, chartDict)
        paramDict = set_up_tab_for_show_or_download_chart(
            dfExport,
            fig,
            configPlotlyDict,
            chartDict,
            metricToPlot + period + xAxisDimension,
            False,
            None,
            xAxisDimension,
            paramDict,
        )
    return paramDict, usedColorDict, chartDict


def mekko_plot(df, chartDict, paramDict, unit_name=None, colors=None, **subplot):
    """A mekko plot is a normalized stacked column plot with variable bar width.

    :param DataFrame df: already indexed by category, with only numeric columns:
                there will be one stacked-bar per line (X), labeled after the index, with one bar per column.
    :param str unit_name: used to populate hover.
    :param list colors: color of each column. None for default palette (blue, red, ...).
    The rest (title..) is easily added afterwards.
    """
    # Normalize then defer to stacked_bar_width_plot plot.
    namingParams = get_naming_params()
    chosenChart = namingParams["chosenChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisSort = namingParams["yAxisSort"]
    xAxisSort = namingParams["xAxisSort"]
    areaSort = namingParams["areaSort"]
    sortAxis = namingParams["sortAxis"]
    aggregateOtherItemsNameKey = namingParams["aggregateOtherItemsName"]
    value_cols, schema = get_schema_and_column_names(df)
    numeric_cols = [c for c, dt in schema.items() if is_numeric_dtype(dt)]
    if not numeric_cols:
        raise pl.exceptions.ComputeError("No numeric data")

    lf = ensure_lazyframe(df)
    total_sum_val = (
        lf.select(pl.sum_horizontal(pl.col(numeric_cols).fill_null(0)).alias("total"))
        .select(pl.col("total").sum())
        .collect()
        .item()
    )
    if total_sum_val == 0:
        raise pl.exceptions.ComputeError("No numeric data")
    sortMetricIsTemporary = False
    if chartDict[chosenChart] == marimekkoChart:
        numeric_cols = [c for c, dt in schema.items() if is_numeric_dtype(dt)]
        value_cols = numeric_cols
        try:
            w = df.with_columns(
                pl.sum_horizontal([pl.col(c) for c in numeric_cols]).alias(unit_name)
            )
        except pl.exceptions.ComputeError:
            if not numeric_cols:
                columns, schema = get_schema_and_column_names(df)
                message = (
                    "No numeric columns found for mekko chart. "
                    f"Schema: {schema}. Sample:\n{df.head(5)}"
                )
                paramDict = add_warning_message_in_plot_charts_tab(paramDict, message)
            raise
        w = w.with_columns([pl.col(c) / pl.col(unit_name) for c in numeric_cols])
        sortMetric = unit_name
    else:
        value_cols = [chartDict[yAxisMetric]]
        w = duplicate_dataframe(df)
        w = w.with_columns(pl.col(chartDict[yAxisMetric]).alias(unit_name))
        sortMetric = unit_name
        if chartDict[sortAxis] == areaSort:
            sortMetric = "__barmekko_area_sort"
            sortMetricIsTemporary = True
            w = w.with_columns(
                (
                    pl.col(chartDict[xAxisMetric]).fill_null(0)
                    * pl.col(chartDict[yAxisMetric]).fill_null(0)
                ).alias(sortMetric)
            )
        elif chartDict[sortAxis] == xAxisSort:
            sortMetric = chartDict[xAxisMetric]
        else:
            sortMetric = chartDict[yAxisMetric]
    w = w.sort(sortMetric)
    if chartDict[chosenChart] == barmekkoChart and sortMetricIsTemporary:
        w = w.drop(sortMetric)
    w = rank_others_as_last(w, aggregateOtherItemsNameKey, 0)
    return stacked_bar_width_plot(
        w,
        chartDict,
        paramDict,
        value_cols,
        width_col=unit_name,
        colors=colors,
        **subplot,
    )


def check_largest_smallest_value_gap(
    df: pl.DataFrame | pl.LazyFrame, colname: str, paramDict: dict
) -> None:
    """Warn when the ratio between max and min values is very large."""

    lf = ensure_lazyframe(df)
    max_val, min_val = (
        lf.select(
            pl.col(colname).max().alias("max_val"),
            pl.col(colname).min().alias("min_val"),
        )
        .collect(engine="streaming")
        .row(0)
    )

    if min_val == 0 or min_val / max_val < 0.01:
        message = (
            "Large difference between max ("
            + str(round(max_val, 1))
            + ") and min ("
            + str(round(min_val, 1))
            + ")"
            + colname
            + " values"
        )
        paramDict = add_warning_message_in_plot_charts_tab(paramDict, message)
        message = "Bar mekko might not plot correctly"
        paramDict = add_warning_message_in_plot_charts_tab(paramDict, message)
        message = "Try setting the Number of Top Items parameter to a lower value "
        paramDict = add_info_message_in_plot_charts_tab(paramDict, message)
    return None


def set_barmekko_params_and_add_trace(
    figure: go.Figure,
    subplot: dict,
    df: pl.DataFrame | pl.LazyFrame,
    colname: str,
    color: str,
    chartDict: dict,
    showValuesAs: str,
    categories: list[str],
    paramDict: dict,
) -> tuple:
    """Add a bar-mekko trace using lazy operations."""
    namingParams = get_naming_params()
    xAxisMetric = namingParams["xAxisMetric"]
    valueName = namingParams["valueName"]
    labelName = namingParams["labelName"]
    rowNameKey = namingParams["rowName"]
    columnNameKey = namingParams["columnName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    orientation = "h"
    width_col = chartDict[xAxisMetric]
    colname_text = str(colname)
    lf = ensure_lazyframe(df)
    lf, chartDict = millify_dataframe(lf, colname, None, labelName, chartDict)
    # BarMekko labels should show values directly, not the legacy "Value" prefix.
    lf = lf.with_columns(
        pl.col(labelName)
        .cast(pl.Utf8)
        .str.replace("^.*?<br>", "")
        .str.replace("^Value<br>", "")
        .str.replace("^Value\\s*", "")
        .str.strip_chars()
        .alias(labelName)
    )
    lf = lf.with_columns(
        pl.when((pl.col(labelName) == "") | (pl.col(labelName) == pl.lit(colname_text)))
        .then(pl.col(colname).round(1).cast(pl.Utf8))
        .otherwise(pl.col(labelName))
        .alias(labelName)
    )
    positions = get_marimekko_positions(
        lf, namingParams["countName"], width_col
    ).select(width_col, "x", "halfColumn", colname, labelName)
    lists = to_lists(positions, [width_col, "x", "halfColumn", labelName, colname])
    width = lists[width_col]
    x = lists["x"]
    halfColumn = lists["halfColumn"]
    text_vals = lists[labelName]
    hover_text_vals = list(text_vals)
    x_vals = lists[colname]
    tickformat = ""
    rangeArray = None
    visible = True
    showticklabels = True
    textposition = "outside"
    textfontcolor = "black"
    tickvals = [xi + wi / 2 for xi, wi in zip(x, width)]
    ticktext = ["%s" % (l) for l in zip(categories)]
    if chartDict.get(plotSmallMultiplesKey):
        total_width = sum(float(value or 0.0) for value in width)
        readable_rows = [is_readable_mekko_row(value, total_width) for value in width]
        text_vals = [
            text if readable else "" for text, readable in zip(text_vals, readable_rows)
        ]
        ticktext = [
            text if readable else "" for text, readable in zip(ticktext, readable_rows)
        ]
    tickrange = [0, sum(width)]
    barmode = "relative"
    bargap = 0
    max_val = get_max_value(positions, colname)
    min_val = get_min_value(positions, colname)
    if max_val == 0 or min_val == 0 or min_val / max_val < 0.01:
        message = (
            "Large difference between max ("
            + str(round(max_val, 1))
            + ") and min ("
            + str(round(min_val, 1))
            + ")"
            + colname
            + " values"
        )
        paramDict = add_warning_message_in_plot_charts_tab(paramDict, message)
        message = "Bar mekko might not plot correctly"
        paramDict = add_warning_message_in_plot_charts_tab(paramDict, message)
        message = "Try setting the Number of Top Items parameter to a lower value "
        paramDict = add_info_message_in_plot_charts_tab(paramDict, message)
    row, col, setColAndRow = 1, 1, False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if rowNameKey in chartDict and chartDict[rowNameKey]:
            row = chartDict[rowNameKey]
            if columnNameKey in chartDict and chartDict[columnNameKey]:
                col = chartDict[columnNameKey]
                setColAndRow = True
    if setColAndRow:
        figure.add_trace(
            go.Bar(
                name=colname,
                x=x_vals,
                y=x,
                width=width,
                marker_color=color,
                marker_line_color="white",
                marker_line_width=1,
                text=text_vals,
                textposition=textposition,
                textangle=0,
                textfont_color=textfontcolor,
                hovertext=hover_text_vals,
                offset=0,
                orientation=orientation,
            ),
            row=row,
            col=col,
        )
    else:
        figure.add_trace(
            go.Bar(
                name=colname,
                x=x_vals,
                y=x,
                width=width,
                marker_color=color,
                marker_line_color="white",
                marker_line_width=1,
                text=text_vals,
                textposition=textposition,
                textangle=0,
                textfont_color=textfontcolor,
                hovertext=hover_text_vals,
                offset=0,
                orientation=orientation,
            ),
            **subplot,
        )
    return (
        figure,
        halfColumn,
        ticktext,
        tickformat,
        rangeArray,
        visible,
        showticklabels,
        tickvals,
        tickrange,
        barmode,
        bargap,
        chartDict,
        row,
        col,
    )


def set_marimekko_params_and_add_trace(
    figure: go.Figure,
    subplot: dict,
    df: pl.DataFrame | pl.LazyFrame,
    colname: str,
    color: str,
    width_col: str,
    chartDict: dict,
    showValuesAs: str,
    categories: list[str],
) -> tuple:
    """Add a marimekko trace from ``df``.

    LazyFrame inputs are collected with ``engine="streaming"`` so that all
    intermediate tables—including tick-label helpers—are gathered efficiently.

    Parameters
    ----------
    df:
        Can be a :class:`polars.DataFrame` or :class:`polars.LazyFrame`.
    """
    namingParams = get_naming_params()
    absolute = namingParams["absolute"]
    percentOfRowTotal = namingParams["percentOfRowTotal"]
    percentOfColumnTotal = namingParams["percentOfColumnTotal"]
    percentOfTotal = namingParams["percentOfTotal"]
    countName = namingParams["countName"]
    showLegend = namingParams["showLegend"]
    showBoth = namingParams["showBoth"]
    showLegendOnTop = namingParams["showLegendOnTop"]
    showLegendInBars = namingParams["showLegendInBars"]
    labelName = namingParams["labelName"]
    rowNameKey = namingParams["rowName"]
    columnNameKey = namingParams["columnName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    orientation = "h"
    lf = ensure_lazyframe(df)
    # Collect marimekko positions only once and reuse the values

    pos_df = calculate_marimekko_positions(lf, countName, width_col).collect(
        engine="streaming"
    )
    columns, _ = get_schema_and_column_names(pos_df)
    width = pos_df[width_col].to_list()
    x = pos_df["x"].to_list()
    halfColumn = pos_df["halfColumn"].to_list()
    tickvals = pos_df["tickval"].to_list()
    tickrange = [0, pos_df[width_col].sum()]
    lf = lf.with_columns(pl.lit(1).alias(countName))
    show = "%of column"
    maxLabelLength = 20

    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        pass
        # chartDict[showLegend]=showLegendInBars
    if showValuesAs in [absolute]:
        df_pl_lazy, chartDict = millify_dataframe(
            lf, width_col, colname, labelName, chartDict
        )
        lf = ensure_lazyframe(df_pl_lazy)
    elif showValuesAs in [percentOfTotal]:
        df_pl_lazy, chartDict = millify_dataframe(
            lf, width_col, colname, labelName, chartDict
        )
        lf = ensure_lazyframe(df_pl_lazy)
    elif showValuesAs in [percentOfRowTotal, percentOfColumnTotal]:
        df_pl_lazy, chartDict = millify_dataframe(
            lf, width_col, colname, labelName, chartDict
        )
        lf = ensure_lazyframe(df_pl_lazy)

    if chartDict[showLegend] in [showBoth, showLegendInBars]:
        trace_label = colname[:maxLabelLength].strip()
        label_text = pl.col(labelName).cast(pl.Utf8).str.strip_chars()
        lf = lf.with_columns(
            pl.when(label_text == "")
            .then(pl.lit(trace_label))
            .otherwise(pl.concat_str([pl.lit(f"{trace_label}<br>"), label_text]))
            .alias(labelName)
        )

    collected = lf.select(
        [pl.col(columns[0]), pl.col(colname), pl.col(labelName), pl.col(countName)]
    ).collect(engine="streaming")
    visible = True
    textposition = "inside"
    textfontcolor = "white"
    barmode = "relative"
    bargap = 0
    tickformat = ""
    rangeArray = None
    showticklabels = True
    insidetextanchor = "middle"
    ticktext = [str(l) for l in categories]
    if chartDict.get(plotSmallMultiplesKey):
        total_width = sum(float(value or 0.0) for value in width)
        ticktext = [
            text if is_readable_mekko_row(value, total_width) else ""
            for text, value in zip(ticktext, width)
        ]
    row, col, setColAndRow = 1, 1, False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        showticklabels = False
        if rowNameKey in chartDict and chartDict[rowNameKey]:
            row = chartDict[rowNameKey]
            if columnNameKey in chartDict and chartDict[columnNameKey]:
                col = chartDict[columnNameKey]
                setColAndRow = True
    text_vals = collected[labelName].to_list()
    hover_text_vals = list(text_vals)
    x_vals = collected[colname].to_list()
    if chartDict.get(plotSmallMultiplesKey):
        text_vals = [
            text if is_readable_mekko_row(value, total_width) else ""
            for text, value in zip(text_vals, width)
        ]

    if setColAndRow:

        figure.add_trace(
            go.Bar(
                name=colname,
                x=x_vals,
                y=x,
                width=width,
                text=text_vals,
                marker_color=color,
                textposition=textposition,
                textangle=0,
                textfont_color=textfontcolor,
                hovertext=hover_text_vals,
                insidetextanchor=insidetextanchor,
                offset=0,
                orientation=orientation,
            ),
            row=row,
            col=col,
        )
    else:
        figure.add_trace(
            go.Bar(
                name=colname,
                x=x_vals,
                y=x,
                width=width,
                text=text_vals,
                marker_color=color,
                textposition=textposition,
                textangle=0,
                textfont_color=textfontcolor,
                hovertext=hover_text_vals,
                insidetextanchor=insidetextanchor,
                offset=0,
                orientation=orientation,
            ),
            **subplot,
        )
    return (
        figure,
        halfColumn,
        ticktext,
        tickformat,
        rangeArray,
        visible,
        showticklabels,
        tickvals,
        tickrange,
        barmode,
        bargap,
        chartDict,
        row,
        col,
    )


def draw_mekko_chart_small_multiples(
    df, column, valueCols, chartDict, paramDict, usedColorDict, xColumn
):
    configParams = get_config_params()
    namingParams = get_naming_params()
    uniformTextMinSize = _get_uniform_text_min_size(configParams, namingParams)
    configPlotlyDict = configParams["configPlotlyDict"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    periodName = namingParams["periodName"]
    xAxisDimensionKey = namingParams["xAxisDimension"]
    yAxisDimensionKey = namingParams["yAxisDimension"]
    secondDimensionItemsArrayKey = namingParams["secondDimensionItemsArray"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    globalAggregateKey = namingParams["globalAggregateKey"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    valueName = namingParams["valueName"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    smallMultiplesDimensionKey = namingParams["smallMultiplesDimension"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    chosenChartKey = namingParams["chosenChart"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    rowName = namingParams["rowName"]
    columnName = namingParams["columnName"]
    toPlotPeriod = chartDict[toPlotPeriod]
    chosenChart = chartDict[chosenChartKey]
    chartDict[plotSmallMultiplesKey] = metConditionValue
    configPlotlyDict = configPlotlyDict[chosenChart]
    smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    dfPanelScope, secondDimensionItems, aggregateOtherItemsName, valueCols = (
        show_only_largest(
            df,
            column,
            chartDict[xAxisDimensionKey],
            xColumn,
            valueCols,
            chartDict,
            paramDict,
            "Y",
        )
    )
    orderMetric = _small_multiple_total_metric_column(
        dfPanelScope, valueCols, chartDict
    )
    if orderMetric:
        secondDimensionItems = order_small_multiple_facets_by_total(
            ensure_lazyframe(dfPanelScope),
            column,
            orderMetric,
            secondDimensionItems,
            aggregateOtherItemsName,
        )
    chartDict = _pin_small_multiple_metric_prefixes(
        dfPanelScope,
        column,
        [
            orderMetric,
            chartDict.get(xAxisMetric),
            chartDict.get(yAxisMetric),
            chartDict.get(namingParams["multipliedMetric"]),
            *valueCols,
        ],
        chartDict,
    )
    dfDump, globalUniqueItems, globalAggregateOtherItemsName, valueCols = (
        show_only_largest(
            df,
            chartDict[xAxisDimensionKey],
            None,
            xColumn,
            valueCols,
            chartDict,
            paramDict,
            "X",
        )
    )
    count, countRows, countCols = 1, 1, 1
    paramDict[secondDimensionItemsArrayKey] = secondDimensionItems
    paramDict[globalUniqueItemsArrayKey] = globalUniqueItems
    paramDict[globalAggregateKey] = globalAggregateOtherItemsName
    paramDict, numberOfCols, numberOfRows = setup_fig_for_mekko_charts(
        df,
        column,
        secondDimensionItems,
        chartDict[xAxisDimensionKey],
        paramDict,
        chartDict,
    )
    fatherAndChildItems = []
    frameArray: list[pl.LazyFrame] = []
    chartDict[rowName], chartDict[columnName] = 1, 1
    chartDict[rowName], chartDict[columnName] = 1, 1
    canPlot = False
    title = ""
    if len(secondDimensionItems) > 1:
        chartDict[numberOfPlottedSmallMultiplesKey] = len(secondDimensionItems)
        for smallMultiplesDimension in secondDimensionItems:
            chartDict[smallMultiplesDimensionKey] = smallMultiplesDimension
            (
                lf_plot,
                metricToPlot,
                colorArray,
                usedColorDict,
                chartDict,
                period,
            ) = prepare_small_multiple_mekko_df(
                df,
                smallMultiplesDimension,
                secondDimensionItems,
                smallMultiplesColumn,
                valueCols,
                chartDict,
                paramDict,
                usedColorDict,
                xColumn,
                globalUniqueItems,
            )
            if is_valid_lazyframe(lf_plot):
                canPlot = True
                frameArray.append(lf_plot)
                columns, schema = get_schema_and_column_names(lf_plot)
                cols_to_use = [
                    c
                    for c in columns
                    if c not in {smallMultiplesColumn, smallMultiplesColumnKey}
                ]
                dfFiltered = lf_plot.select(cols_to_use)
                fig, dfNegative, negativeValuesMessage, chartDict = mekko_plot(
                    dfFiltered,
                    chartDict,
                    paramDict,
                    unit_name=valueName,
                    colors=colorArray,
                )
                count, countRows, countCols, chartDict = reset_row_and_column_counters(
                    count,
                    countCols,
                    countRows,
                    numberOfCols,
                    numberOfRows,
                    chartDict,
                )
        lf_all = (
            pl.concat(frameArray, how="diagonal")
            if frameArray
            else pl.DataFrame().lazy()
        )
        dfPlot = lf_all.collect(engine="streaming") if frameArray else pl.DataFrame()
        if dfPlot.height > 0:
            columns, schema = get_schema_and_column_names(dfPlot)
            numeric_cols = [c for c, dt in schema.items() if dt.is_numeric()]
            if numeric_cols:
                totals = (
                    dfPlot.with_columns(
                        total=pl.sum_horizontal(pl.col(numeric_cols).fill_null(0))
                    )
                    .group_by(smallMultiplesColumn)
                    .agg(pl.col("total").sum())
                )
                max_value = totals["total"].max()
            else:
                max_value = 0
        else:
            max_value = 0
        if fig is not None:
            fig = _update_small_multiple_mekko_axes(
                fig, chosenChart, barmekkoChart, max_value
            )
            fig = _center_subplot_titles(fig, secondDimensionItems)
        if canPlot:
            if (
                chosenChart == marimekkoChart
                and chartDict.get(xAxisDimensionKey)
                and chartDict.get(yAxisDimensionKey)
            ):
                title, paramDict, chartDict = (
                    make_marimekko_and_stacked_bar_chart_title(
                        df,
                        chosenChart,
                        paramDict,
                        chartDict[xAxisDimensionKey],
                        metricToPlot,
                        chartDict,
                        toPlotPeriod,
                        chartDict[yAxisDimensionKey],
                    )
                )
            elif chartDict.get(xAxisDimensionKey):
                title, paramDict, chartDict = (
                    make_marimekko_and_stacked_bar_chart_title(
                        df,
                        chosenChart,
                        paramDict,
                        chartDict[xAxisDimensionKey],
                        metricToPlot,
                        chartDict,
                        toPlotPeriod,
                        chartDict[xAxisMetric],
                    )
                )
            uniformTextMinSize = 9
            if fig is not None:
                fig.update_layout(
                    uniformtext=dict(mode="hide", minsize=uniformTextMinSize),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                fig, message = get_user_message(
                    fig,
                    chosenChart,
                    toPlotPeriod,
                    column,
                    paramDict,
                    chartDict,
                    dfFiltered,
                    None,
                    None,
                )
                fig = add_message_as_annotation(
                    fig, message, None, chosenChart, chartDict, paramDict
                )
                fig = add_title_as_annotation(fig, title, chosenChart, chartDict)
                fig = enable_draw_shapes(fig)
            check_small_multiples_total(dfPlot, df, metricToPlot, chartDict)
            if (
                chosenChart == marimekkoChart
                and chartDict.get(xAxisDimensionKey)
                and chartDict.get(yAxisDimensionKey)
            ):
                paramDict = set_up_tab_for_show_or_download_chart(
                    dfPlot,
                    fig,
                    configPlotlyDict,
                    chartDict,
                    chartDict[xAxisDimensionKey]
                    + chartDict[yAxisDimensionKey]
                    + toPlotPeriod
                    + metricToPlot,
                    False,
                    None,
                    None,
                    paramDict,
                )
            elif chosenChart == barmekkoChart and chartDict.get(xAxisDimensionKey):
                paramDict = set_up_tab_for_show_or_download_chart(
                    dfPlot,
                    fig,
                    configPlotlyDict,
                    chartDict,
                    smallMultiplesColumn
                    + chartDict[xAxisMetric]
                    + toPlotPeriod
                    + metricToPlot,
                    False,
                    None,
                    None,
                    paramDict,
                )
            if negativeValuesMessage:
                paramDict = add_warning_message_in_plot_charts_tab(
                    paramDict, negativeValuesMessage
                )
        else:
            paramDict = add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return usedColorDict, paramDict, chartDict


def draw_mekko_chart(
    df, column, valueCols, chartDict, paramDict, usedColorDict, xColumn
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    paramDictCopy = copy.deepcopy(paramDict)
    if column == totalName:
        usedColorDict, paramDict = draw_mekko_chart_total(
            df, column, valueCols, chartDict, paramDict, usedColorDict, xColumn
        )
    elif column != totalName:
        usedColorDict, paramDict, chartDict = draw_mekko_chart_small_multiples(
            df, column, valueCols, chartDict, paramDict, usedColorDict, xColumn
        )
    return usedColorDict, paramDict, chartDict


def draw_mekko_chart_total(
    df, column, valueCols, chartDict, paramDict, usedColorDict, xColumn
):
    configParams = get_config_params()
    namingParams = get_naming_params()
    uniformTextMinSize = _get_uniform_text_min_size(configParams, namingParams)
    weekName = namingParams["weekName"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    periodName = namingParams["periodName"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    valueName = namingParams["valueName"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    chosenChart = namingParams["chosenChart"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    toPlotPeriod = chartDict[toPlotPeriod]
    chosenChart = chartDict[chosenChart]
    configPlotlyDict = configParams["configPlotlyDict"]
    configPlotlyDict = configPlotlyDict[chosenChart]
    selectedPeriods = namingParams["selectedPeriods"]
    periodOrder = chartDict[selectedPeriods]
    smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    usedColorDict = {}
    namingParams = get_naming_params()
    (
        dfFiltered,
        metricToPlot,
        colorArray,
        usedColorDict,
        chartDict,
        period,
        uniqueItems,
    ) = prepare_data_for_width_plot(
        df, toPlotPeriod, valueCols, chartDict, paramDict, usedColorDict
    )
    dfFiltered = ensure_polars_df(dfFiltered)
    if get_row_count(dfFiltered) > 0:
        fig, dfNegative, negativeValuesMessage, chartDict = mekko_plot(
            dfFiltered, chartDict, paramDict, unit_name=valueName, colors=colorArray
        )
        if chosenChart == marimekkoChart:
            title, paramDict, chartDict = make_marimekko_and_stacked_bar_chart_title(
                df,
                chosenChart,
                paramDict,
                chartDict[xAxisDimension],
                metricToPlot,
                chartDict,
                toPlotPeriod,
                chartDict[yAxisDimension],
            )

            fig = show_total_percent(
                fig, df, dfFiltered, period, metricToPlot, chartDict
            )

        else:
            title, paramDict, chartDict = make_marimekko_and_stacked_bar_chart_title(
                df,
                chosenChart,
                paramDict,
                chartDict[xAxisDimension],
                metricToPlot,
                chartDict,
                toPlotPeriod,
                chartDict[xAxisMetric],
            )
        if fig is not None:
            fig.update_layout(
                uniformtext=dict(mode="hide", minsize=uniformTextMinSize),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            fig, message = get_user_message(
                fig,
                chosenChart,
                period,
                column,
                paramDict,
                chartDict,
                dfFiltered,
                None,
                None,
            )
            fig = add_message_as_annotation(
                fig, message, None, chosenChart, chartDict, paramDict
            )
            fig = add_title_as_annotation(fig, title, chosenChart, chartDict)
            fig = enable_draw_shapes(fig)
        if (
            chosenChart == marimekkoChart
            and chartDict[xAxisDimension]
            and chartDict[yAxisDimension]
        ):
            paramDict = set_up_tab_for_show_or_download_chart(
                dfFiltered,
                fig,
                configPlotlyDict,
                chartDict,
                chartDict[xAxisDimension]
                + chartDict[yAxisDimension]
                + period
                + metricToPlot,
                False,
                None,
                None,
                paramDict,
            )
        elif chosenChart == barmekkoChart and chartDict[xAxisDimension]:
            paramDict = set_up_tab_for_show_or_download_chart(
                dfFiltered,
                fig,
                configPlotlyDict,
                chartDict,
                smallMultiplesColumn + chartDict[xAxisMetric] + period + metricToPlot,
                False,
                None,
                None,
                paramDict,
            )
        if negativeValuesMessage:
            paramDict = add_warning_message_in_plot_charts_tab(
                paramDict, negativeValuesMessage
            )
    return usedColorDict, paramDict
