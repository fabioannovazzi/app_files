import copy
import logging
import math
from typing import Any, Mapping, Sequence

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.adjust_position import (
    adjust_ax_by_number_of_columns,
    get_x_shift_for_data_column,
)
from modules.charting.chart_primitives import (
    change_metric_if_cost_analysis,
    divide_by_value_prefix,
    get_color_dictionary,
    get_hightlight_color,
    get_number_prefix,
    make_text_position_array,
    millify,
    millify_dataframe,
    multiply_other_metric_for_scale,
)
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui


def _log_debug(*args: object) -> None:
    """Log debugging information without requiring UI."""

    if st is not None and hasattr(st, "write"):
        ui.write(*args)
    else:  # pragma: no cover - fallback for environments without UI
        logging.info(" ".join(str(a) for a in args))


try:
    from modules.charting.polars_helpers import collect_tail, to_lists
except Exception as e:  # pragma: no cover - provide fallback for tests
    logging.exception(e)
    _log_debug("draw_charts_utils import error:", e)

    def collect_tail(
        lf: pl.LazyFrame | pl.DataFrame, n: int, *, engine: str = "streaming"
    ) -> pl.DataFrame:
        """Return the last ``n`` rows from ``lf`` as a ``DataFrame``.

        The original implementation lives in
        ``modules.charting.polars_helpers``.  This lightweight fallback keeps
        the tests independent from that module while preserving behaviour for
        both :class:`~polars.DataFrame` and :class:`~polars.LazyFrame` inputs.
        """

        if isinstance(lf, pl.DataFrame):
            return lf.tail(n)
        return lf.tail(n).collect(engine=engine)

    def to_lists(lf: pl.LazyFrame, cols: list[str]) -> dict[str, list]:
        """Collect ``cols`` from ``lf`` into Python lists.

        This mirrors ``polars_helpers.to_lists`` but avoids importing that
        helper during tests where the full module is intentionally absent.
        """

        return {
            c: lf.select(pl.col(c)).collect(engine="streaming")[c].to_list()
            for c in cols
        }


from modules.layout.memoization import check_collect
from modules.utilities import utils

MEKKO_MIN_ROW_SHARE_FOR_LABEL = 0.02


def is_readable_mekko_row(category_width: Any, total_width: Any) -> bool:
    """Return whether a Mekko row has enough visual height for labels."""

    try:
        category_width_value = abs(float(category_width or 0.0))
        total_width_value = abs(float(total_width or 0.0))
    except (TypeError, ValueError):
        return False
    if total_width_value <= 0:
        return False
    return category_width_value / total_width_value >= MEKKO_MIN_ROW_SHARE_FOR_LABEL


is_readable_barmekko_row = is_readable_mekko_row


try:  # pragma: no cover - config helpers may be stubbed in tests
    from modules.utilities.config import (
        get_config_params,
        get_metric_array_params,
        get_naming_params,
    )
except Exception as e:  # pragma: no cover - provide minimal fallbacks
    logging.exception(e)
    ui.error("Something went wrong while importing draw_charts_utils.")
    from modules.utilities.config import get_config_params, get_naming_params

    def get_metric_array_params() -> dict:  # type: ignore[override]
        """Return empty metric parameter mapping when config is limited."""

        return {}


from modules.utilities.error_messages import add_info_message_in_plot_charts_tab
from modules.utilities.utils import ensure_lazyframe

try:
    from modules.utilities.helpers import (
        coerce_numeric_columns,
        drop_columns,
        duplicate_dataframe,
        is_numeric_dtype,
        unique,
    )
except Exception as e:
    logging.exception(e)
    ui.error("Something went wrong while importing draw_charts_utils.")
    from modules.utilities.helpers import drop_columns, duplicate_dataframe, unique

    def coerce_numeric_columns(df: pl.DataFrame) -> pl.DataFrame:
        return df

    def is_numeric_dtype(dt: pl.DataType) -> bool:
        return getattr(dt, "is_numeric", lambda: False)()


try:
    from modules.utilities.utils import (
        ensure_lazyframe,
        ensure_polars_df,
        get_schema_and_column_names,
    )
except Exception as e:  # pragma: no cover - provide minimal fallback
    logging.exception(e)
    ui.error("Something went wrong while importing draw_charts_utils.")
    from modules.utilities.utils import (
        ensure_lazyframe,
        get_schema_and_column_names,
    )

    def ensure_polars_df(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
        """Return a concrete ``DataFrame`` from ``df``.

        This mirrors ``modules.utilities.utils.ensure_polars_df`` but avoids an
        import error when the utilities module is heavily stubbed in tests.
        """

        return df if isinstance(df, pl.DataFrame) else df.collect(engine="streaming")


try:  # pragma: no cover - optional dependency during testing
    from modules.utilities.utils import extract_scalar
except Exception as e:  # pragma: no cover - fallback if missing
    logging.exception(e)
    ui.error("Something went wrong while importing draw_charts_utils.")

    def extract_scalar(obj: Any) -> float:
        return float(getattr(obj, "item", lambda: obj)())


try:  # pragma: no cover - optional dependency during testing
    from modules.utilities.utils import get_uniform_text_min_size
except Exception as e:  # pragma: no cover - fallback if missing
    logging.exception(e)
    _log_debug("draw_charts_utils import error:", e)

    def get_uniform_text_min_size(config_params: dict, naming_params: dict) -> int:
        """Return the configured minimum uniform text size."""

        key = naming_params["uniformTextMinSize"]
        return int(config_params[key])


def add_empty_rows_to_df(
    df: pl.DataFrame | pl.LazyFrame,
    column: str | Any,
    uniqueItemsNumber: int,
    maxItems: int,
) -> pl.LazyFrame:
    """Return ``df`` with additional blank rows when ``maxItems`` exceeds ``uniqueItemsNumber``.

    The helper is intentionally resilient to a variety of input types so it can
    be used in lightweight testing environments where only a subset of utility
    functions are available.
    """

    naming_params = get_naming_params()
    placeholder = naming_params["invisibleCharacter"]

    # ``column`` may be provided as a non-string object (``Path``, ``Enum``, etc.)
    # but downstream logic relies on string operations.  Coerce to ``str`` early
    # so helper utilities that may use ``.endswith`` or similar methods never
    # encounter an ``AttributeError``.
    column_name = column if isinstance(column, str) else str(column)

    # Normalise input to ``LazyFrame``.  Falling back to constructing a new
    # ``DataFrame`` keeps the function compatible with generic sequences of
    # mappings used in tests.
    if isinstance(df, pl.LazyFrame):
        lf = df
    elif isinstance(df, pl.DataFrame):
        lf = df.lazy()
    else:
        try:
            lf = pl.DataFrame(df).lazy()
        except Exception as e:  # noqa: BLE001
            logging.exception(e)
            raise TypeError(f"Unsupported object type: {type(df)!r}") from e

    columns, schema = get_schema_and_column_names(lf)
    if schema and not isinstance(schema, Mapping):
        schema = dict(schema)

    # Ensure we operate purely on textual column names.  ``get_schema_and_column_names``
    # may return non-string keys depending on input; convert everything to ``str`` to
    # avoid attribute errors when helper utilities use string-only methods.
    columns = [str(c) for c in columns]
    schema = {str(k): v for k, v in (schema.items() if schema else [])}
    dtype = schema.get(column_name) if schema else None

    # Ensure the target column exists and is of string type so that the
    # placeholder markers below are valid.
    if column_name not in columns:
        lf = lf.with_columns(pl.lit(None).alias(column_name))
        columns.append(column_name)
    elif dtype != pl.Utf8:
        lf = lf.with_columns(pl.col(column_name).cast(pl.Utf8))

    if uniqueItemsNumber >= maxItems:
        return lf

    blank_template = {c: [None] for c in columns}
    frames: list[pl.LazyFrame] = [lf]
    for i in range(maxItems - uniqueItemsNumber):
        blank_row = (
            pl.DataFrame(blank_template)
            .with_columns(pl.lit(placeholder * (i + 1)).alias(column_name))
            .lazy()
        )
        frames.append(blank_row)

    return pl.concat(frames, how="vertical")


def get_maximum_number_of_items_in_small_multiples(
    df: pl.DataFrame | pl.LazyFrame,
    columnsToPlotNoTotal: Sequence[str],
    chartDict: dict,
) -> int:
    """Return the maximum unique count across ``columnsToPlotNoTotal``."""

    namingParams = get_naming_params()
    numberOfTop: int | None = None
    numberOfTopKey = namingParams["numberOfTop"]
    if "X" in chartDict and numberOfTopKey in chartDict["X"]:
        numberOfTop = chartDict["X"][numberOfTopKey] + 1

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df

    maxItems = 0
    for column in columnsToPlotNoTotal:
        unique_cnt = (
            lf.select(pl.col(column).n_unique()).collect(engine="streaming").item()
        )
        if numberOfTop is None:
            maxItems = max(maxItems, unique_cnt)
        elif numberOfTop <= unique_cnt:
            maxItems = numberOfTop
        elif unique_cnt < numberOfTop and maxItems < unique_cnt:
            maxItems = unique_cnt
    return maxItems


def prepare_value_labels_for_timeline(
    dfCopy,
    chosenChart: str,
    column: str,
    labelArray: list[str],
    yShiftArray: list[str],
    xShiftArray: list[str],
    chartDict: dict,
    count: int,
) -> pl.DataFrame | pl.LazyFrame:
    """Add min/max labels and shifts for timeline charts using Polars."""

    namingParams = get_naming_params()
    timelineChart = namingParams["timelineChart"]
    slopeChart = namingParams["slopeChart"]
    areaChart = namingParams["areaChart"]
    labelName = namingParams["labelName"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]

    is_lazy = isinstance(dfCopy, pl.LazyFrame)
    lf = ensure_lazyframe(duplicate_dataframe(dfCopy))

    label_col = labelArray[count]
    y_col = yShiftArray[count]
    x_col = xShiftArray[count]

    lf = lf.with_columns(
        [
            pl.lit("").alias(label_col),
            pl.lit(0).alias(y_col),
            pl.lit(0).alias(x_col),
        ]
    )

    if chosenChart in [timelineChart, areaChart]:
        lf = lf.with_columns(pl.col(column).fill_null(0))
        stats = (
            lf.select(
                pl.col(column).min().alias("_min"),
                pl.col(column).max().alias("_max"),
                pl.col(column).first().alias("_first"),
                pl.col(column).last().alias("_last"),
                pl.len().alias("_len"),
            )
            .collect(engine="streaming")
            .row(0)
        )
        min_v, max_v, first_v, last_v, length = stats
        last_idx = length - 1
        max_idx = last_idx
        if chosenChart == areaChart:
            max_idx_value = (
                lf.with_row_index("__idx")
                .filter(pl.col(column) == max_v)
                .select(pl.col("__idx").first().alias("_max_idx"))
                .collect(engine="streaming")
                .item()
            )
            max_idx = int(max_idx_value) if max_idx_value is not None else last_idx

        if (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] != absolute
        ):
            first_label = first_v
            last_label = last_v
            min_label = min_v
            max_label = max_v
        else:
            first_label = divide_by_value_prefix(first_v, chartDict, False)
            last_label = divide_by_value_prefix(last_v, chartDict, False)
            min_label = divide_by_value_prefix(min_v, chartDict, False)
            max_label = divide_by_value_prefix(max_v, chartDict, False)

        if chosenChart == areaChart:
            # Static stacked areas use right-end direct labels plus one peak
            # label; first/min/repeated labels quickly overlap.
            lf = (
                lf.with_row_index("__idx")
                .with_columns(
                    [
                        pl.when(
                            (pl.col("__idx") == max_idx)
                            & (pl.col("__idx") != last_idx)
                            & (pl.col("__idx") != 0)
                        )
                        .then(pl.lit(max_label))
                        .when(pl.col("__idx") == last_idx)
                        .then(pl.lit(last_label))
                        .otherwise(pl.lit(""))
                        .alias(label_col),
                        pl.when(pl.col("__idx") == last_idx)
                        .then(pl.lit(25))
                        .otherwise(pl.col(x_col))
                        .alias(x_col),
                        pl.lit(0).alias(y_col),
                    ]
                )
                .drop("__idx")
            )
        else:
            lf = (
                lf.with_row_index("__idx")
                .with_columns(
                    [
                        pl.when(pl.col("__idx") == 0)
                        .then(pl.lit(first_label))
                        .when(pl.col("__idx") == last_idx)
                        .then(pl.lit(last_label))
                        .when(pl.col(column) == min_v)
                        .then(pl.lit(min_label))
                        .when(pl.col(column) == max_v)
                        .then(pl.lit(max_label))
                        .otherwise(pl.col(label_col))
                        .alias(label_col),
                        pl.when(pl.col("__idx") == 0)
                        .then(pl.lit(18))
                        .when(pl.col("__idx") == last_idx)
                        .then(pl.lit(-18))
                        .otherwise(pl.col(x_col))
                        .alias(x_col),
                        pl.when(pl.col(column) == min_v)
                        .then(pl.lit(-12))
                        .when(pl.col(column) == max_v)
                        .then(pl.lit(12))
                        .otherwise(pl.col(y_col))
                        .alias(y_col),
                    ]
                )
                .drop("__idx")
            )
    elif chosenChart in [slopeChart]:
        stats = (
            lf.select(
                pl.col(column).first().alias("_first"),
                pl.col(column).last().alias("_last"),
                pl.len().alias("_len"),
            )
            .collect(engine="streaming")
            .row(0)
        )
        first_v, last_v, length = stats
        last_idx = length - 1

        def format_slope_endpoint(value):
            if value is None:
                return ""
            try:
                if math.isnan(float(value)):
                    return ""
            except (TypeError, ValueError):
                return ""
            return divide_by_value_prefix(value, chartDict, False)

        first_label = format_slope_endpoint(first_v)
        last_label = format_slope_endpoint(last_v)

        lf = (
            lf.with_row_index("__idx")
            .with_columns(
                [
                    pl.when(pl.col("__idx") == 0)
                    .then(pl.lit(first_label))
                    .when(pl.col("__idx") == last_idx)
                    .then(pl.lit(last_label))
                    .otherwise(pl.col(labelArray[count]))
                    .alias(labelArray[count]),
                    pl.when(pl.col("__idx") == 0)
                    .then(pl.lit(-28))
                    .when(pl.col("__idx") == last_idx)
                    .then(pl.lit(28))
                    .otherwise(pl.col(xShiftArray[count]))
                    .alias(xShiftArray[count]),
                ]
            )
            .drop("__idx")
        )

    return lf if is_lazy else lf.collect()


def add_labels_to_area_chart(
    fig: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    dfCumSum: pl.DataFrame | pl.LazyFrame,
    element: str,
    uniqueItems: list[str],
    labelArray: list[str],
    yShiftArray: list[str],
    xShiftArray: list[str],
    count: int,
    countRows: int,
    countCols: int,
) -> go.Figure:
    """Add annotations to a stacked area chart."""

    naming_params = get_naming_params()
    date_name = naming_params["dateName"]
    df_lazy = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(df_lazy)

    label_col = labelArray[count]
    xshift_col = xShiftArray[count]
    col_name = uniqueItems[count]
    x_expr = (
        pl.col(date_name).alias("__x")
        if date_name in columns
        else pl.int_range(0, pl.len()).alias("__x")
    )
    previous_cols = [item for item in uniqueItems[:count] if item in columns]
    below_expr = (
        pl.sum_horizontal([pl.col(item).fill_null(0) for item in previous_cols])
        if previous_cols
        else pl.lit(0)
    )

    y_expr = (below_expr + (pl.col(col_name).fill_null(0) * 0.5)).alias("__y")

    out = df_lazy.select(
        x_expr,
        pl.col(label_col).alias("__label"),
        pl.col(xshift_col).alias("__xshift"),
        y_expr,
    ).collect(engine="streaming")

    ann_df = out.filter(pl.col("__label") != "")
    labels = ann_df.get_column("__label").to_list()
    xs = ann_df.get_column("__x").to_list()
    xshifts = ann_df.get_column("__xshift").to_list()
    ys = ann_df.get_column("__y").to_list()

    for label, x_val, xshift_val, y_val in zip(labels, xs, xshifts, ys):
        fig.add_annotation(
            text=label,
            showarrow=False,
            x=x_val,
            xshift=xshift_val,
            xref="x",
            align="center",
            yshift=0,
            y=y_val,
            yref="y",
            hovertext=f"{label} {element[:-6]}",
            row=countRows,
            col=countCols,
        )

    return fig


def _stacked_bar_overlay_y_values(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict
) -> list[Any]:
    """Return the categorical y-axis values used by stacked-bar overlays."""

    namingParams = get_naming_params()
    xAxisDimension = namingParams["xAxisDimension"]
    periodName = namingParams["periodName"]
    configured = chartDict.get(xAxisDimension)
    columns, schema = get_schema_and_column_names(df)
    category_col = configured if configured in columns else None
    if category_col is None:
        for column in columns:
            dtype = schema.get(column)
            if (
                column != periodName
                and dtype is not None
                and not is_numeric_dtype(dtype)
            ):
                category_col = column
                break
    if category_col is None:
        return (
            ensure_lazyframe(df)
            .select(pl.arange(0, pl.len()).alias("_y"))
            .collect(engine="streaming")["_y"]
            .to_list()
        )
    return (
        ensure_lazyframe(df)
        .select(pl.col(category_col).cast(pl.Utf8).alias("_y"))
        .collect(engine="streaming")["_y"]
        .to_list()
    )


def _has_plotted_value(value: Any) -> bool:
    """Return whether a Plotly bar value represents a real plotted column."""

    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


def _as_plotly_array(value: Any, length: int, default: Any = None) -> list[Any]:
    """Return a Plotly trace scalar/list attribute as a Python list."""

    if value is None:
        return [default] * length
    if isinstance(value, (str, bytes)):
        return [value] * length
    try:
        values = list(value)
    except TypeError:
        return [value] * length
    if len(values) == length:
        return values
    if not values:
        return [default] * length
    return [values[0]] * length


def _column_center_from_trace(
    x_value: Any,
    width_value: Any,
    offset_value: Any,
) -> Any:
    """Return the rendered center of a legacy Plotly column."""

    if offset_value is None:
        return x_value
    try:
        half_width = 0.5 if width_value is None else width_value / 2.0
        return x_value + offset_value + half_width
    except TypeError:
        return x_value


def _column_bounds_from_trace(
    x_value: Any,
    width_value: Any,
    offset_value: Any,
) -> tuple[Any, Any] | None:
    """Return the rendered left/right bounds of a legacy Plotly column."""

    width = 1 if width_value is None else width_value
    try:
        if offset_value is None:
            return x_value - width / 2.0, x_value + width / 2.0
        return x_value + offset_value, x_value + offset_value + width
    except TypeError:
        return None


def _stacked_column_plot_edge_x(fig: go.Figure, side: str = "right") -> Any | None:
    """Return the first/last rendered x edge for the visible column area."""

    bar_traces = [
        trace for trace in fig.data if str(getattr(trace, "type", "") or "") == "bar"
    ]
    if not bar_traces:
        return None

    reference_trace = bar_traces[-1]
    x_values = list(getattr(reference_trace, "x", []) or [])
    if not x_values:
        return None
    width_values = _as_plotly_array(
        getattr(reference_trace, "width", None), len(x_values)
    )
    offset_values = _as_plotly_array(
        getattr(reference_trace, "offset", None), len(x_values)
    )

    plotted_indexes: list[int] = []
    for index in range(len(x_values)):
        for trace in bar_traces:
            trace_y = list(getattr(trace, "y", []) or [])
            if index < len(trace_y) and _has_plotted_value(trace_y[index]):
                plotted_indexes.append(index)
                break
    if not plotted_indexes:
        return None

    index = plotted_indexes[0] if side == "left" else plotted_indexes[-1]
    bounds = _column_bounds_from_trace(
        x_values[index],
        width_values[index],
        offset_values[index],
    )
    if bounds is None:
        return None
    return bounds[0] if side == "left" else bounds[1]


def _is_readable_stacked_pareto_segment(value: Any) -> bool:
    """Return whether a stacked Pareto segment has room for visible labeling."""

    min_segment_share = 0.035
    try:
        return abs(float(value)) >= min_segment_share
    except (TypeError, ValueError):
        return False


def _stacked_column_overlay_x_values(
    fig: go.Figure, y_values: list[Any]
) -> tuple[list[Any], list[int]] | None:
    """Return legacy stacked-column center x positions for the overlay trace."""

    bar_traces = [
        trace for trace in fig.data if str(getattr(trace, "type", "") or "") == "bar"
    ]
    if not bar_traces:
        return None

    reference_trace = bar_traces[-1]
    x_values = list(getattr(reference_trace, "x", []) or [])
    if len(x_values) != len(y_values):
        return None
    width_values = _as_plotly_array(
        getattr(reference_trace, "width", None), len(x_values)
    )
    offset_values = _as_plotly_array(
        getattr(reference_trace, "offset", None), len(x_values)
    )

    plotted_indexes: list[int] = []
    for index in range(len(x_values)):
        has_bar_at_index = False
        for trace in bar_traces:
            trace_y = list(getattr(trace, "y", []) or [])
            if index < len(trace_y) and _has_plotted_value(trace_y[index]):
                has_bar_at_index = True
                break
        if has_bar_at_index:
            plotted_indexes.append(index)

    center_x_values: list[Any] = []
    for index in plotted_indexes:
        center_x_values.append(
            _column_center_from_trace(
                x_values[index],
                width_values[index],
                offset_values[index],
            )
        )
    return center_x_values, plotted_indexes


def add_overlay_trace(fig, dfCopy, colorArray, chartDict, row, col):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    overlayChartDfKey = namingParams["overlayChartDf"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    countName = namingParams["countName"]
    highlightOverlayChart = namingParams["highlightOverlayChart"]
    labelName = namingParams["labelName"]
    chosenChart = namingParams["chosenChart"]
    metricsToPlot = namingParams["metricsToPlot"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    chosenChart = chartDict[chosenChart]
    df = duplicate_dataframe(dfCopy)
    if overlayChartDfKey in chartDict:
        _overlay = chartDict[overlayChartDfKey]
        from modules.utilities.utils import get_row_count

        overlay_len = get_row_count(_overlay)
        if overlay_len > 0:
            overlayChartDf = ensure_lazyframe(_overlay)
            colorDict = get_color_dictionary(chartDict)
            chosenColor = colorArray[1]
            if highlightOverlayChart in chartDict and chartDict[highlightOverlayChart]:
                chosenColor = get_hightlight_color(chartDict, colorDict)
            overlayMetric = chartDict[overlayChartMetricKey]
            left_cols, _ = get_schema_and_column_names(df)
            right_cols, _ = get_schema_and_column_names(overlayChartDf)
            common_cols = [
                col for col in left_cols if col in right_cols and col != overlayMetric
            ]
            row_id = "__overlay_row_id__"
            if common_cols:
                df = (
                    df.with_row_index(name=row_id)
                    .join(overlayChartDf, on=common_cols, how="left")
                    .sort(row_id)
                    .drop(row_id)
                )
            else:
                # Fall back to row-order alignment when no shared key is available.
                df = (
                    df.with_row_index(name=row_id)
                    .join(
                        overlayChartDf.with_row_index(name=row_id),
                        on=row_id,
                        how="left",
                    )
                    .sort(row_id)
                    .drop(row_id)
                )
            df, chartDict = millify_dataframe(
                df, overlayMetric, None, labelName, chartDict
            )
            textfontcolor = chosenColor
        text_values = []
        if chosenChart in [stackedColumnChart]:
            columns, _ = get_schema_and_column_names(df)
            if countName not in columns:
                df = df.with_columns(pl.lit(1).alias(countName))
            y = (
                df.select(pl.col(overlayMetric))
                .collect(engine="streaming")[overlayMetric]
                .to_list()
            )
            text_values = (
                df.select(pl.col(labelName))
                .collect(engine="streaming")[labelName]
                .to_list()
            )
            aligned_x = _stacked_column_overlay_x_values(fig, y)
            if aligned_x is None:
                x_expr = pl.col(countName).cum_sum().shift(1).fill_null(0)
                x = (
                    df.select(x_expr.alias("_x"))
                    .collect(engine="streaming")["_x"]
                    .to_list()
                )
            else:
                x, plotted_indexes = aligned_x
                y = [y[index] for index in plotted_indexes]
                text_values = [text_values[index] for index in plotted_indexes]
            xaxis = "x"
            yaxis = "y2"
            mode = "lines+markers+text"
            textposition = "bottom center"
            symbol = "square"
            symbolSize = 6
        elif chosenChart in [stackedBarChart]:
            if overlayMetric in percentMetricsArray + growthMetricArray:
                chosenColor = colorDict["redColor"]
            y = _stacked_bar_overlay_y_values(df, chartDict)
            x = (
                df.select(pl.col(overlayMetric))
                .collect(engine="streaming")[overlayMetric]
                .to_list()
            )
            mode = "markers+text"
            xaxis = "x2"
            yaxis = "y"
            textposition = "middle center"
            symbol = "circle"
            symbolSize = 28
            textfontcolor = "white"
            if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts]:
                df = multiply_other_metric_for_scale(
                    df, overlayMetric, chartDict, row, col
                )
                x = (
                    df.select(pl.col(overlayMetric))
                    .collect(engine="streaming")[overlayMetric]
                    .to_list()
                )
                symbolSize = 28
            if chartDict[metricsToPlot][1] in percentMetricsArray + growthMetricArray:
                df = df.with_columns(
                    pl.concat_str(
                        [
                            pl.col(labelName)
                            .cast(pl.Float64, strict=False)
                            .round(0)
                            .cast(pl.Int64, strict=False)
                            .cast(pl.Utf8),
                            pl.lit("%"),
                        ]
                    ).alias(labelName)
                )
        showgrid = False
        tickvals = None
        tickmode = None
        ticktext = None
        if not text_values:
            text_values = (
                df.select(pl.col(labelName))
                .collect(engine="streaming")[labelName]
                .to_list()
            )
        fig.add_trace(
            go.Scatter(
                y=y,
                x=x,
                showlegend=False,
                mode=mode,
                marker=dict(
                    color=chosenColor,
                    size=symbolSize,
                    symbol=symbol,
                    line=dict(width=2, color=chosenColor),
                ),
                xaxis=xaxis,
                yaxis=yaxis,
                text=text_values,
                textposition=textposition,
                textfont=dict(
                    color=textfontcolor, size=10
                ),  # Adjust the size value as needed
            ),
            row=row,
            col=col,
        )
        if chosenChart in [stackedColumnChart]:
            fig.update_layout(
                yaxis2={
                    "overlaying": "y",
                    "side": "right",
                    "showgrid": showgrid,
                    "rangemode": "tozero",
                    "tickvals": tickvals,
                    "tickmode": tickmode,
                    "ticktext": ticktext,
                    "showticklabels": False,
                    "showline": False,
                    "zeroline": False,
                    "ticks": "",
                }
            )
        elif chosenChart in [stackedBarChart]:
            if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts]:
                fig.update_layout(
                    xaxis={
                        "showgrid": showgrid,
                        "rangemode": "tozero",
                        "tickvals": tickvals,
                        "tickmode": tickmode,
                        "ticktext": ticktext,
                        "showticklabels": False,
                        "ticks": "",
                    },
                    xaxis3={
                        "showgrid": showgrid,
                        "rangemode": "tozero",
                        "tickvals": tickvals,
                        "tickmode": tickmode,
                        "ticktext": ticktext,
                        "showticklabels": False,
                        "ticks": "",
                    },
                )
            else:
                fig.update_layout(
                    xaxis2={
                        "overlaying": "x",
                        "showgrid": showgrid,
                        "rangemode": "tozero",
                        "tickvals": tickvals,
                        "tickmode": tickmode,
                        "ticktext": ticktext,
                        "showticklabels": False,
                        "showline": False,
                        "zeroline": False,
                        "ticks": "",
                    }
                )
    return fig, chartDict


def show_total_percent(fig, df, dfFiltered, period, metricToPlot, chartDict):
    """Annotate ``fig`` with the share of ``metricToPlot`` for ``period``."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    valueName = namingParams["valueName"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]

    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        return fig

    lf_filtered = ensure_lazyframe(dfFiltered)
    lf_full = ensure_lazyframe(df)
    percentShown = 100
    columns, _ = get_schema_and_column_names(lf_filtered)
    if valueName in columns:
        metrics_lf = lf_filtered.select(
            pl.col(valueName).sum().alias("totalShown")
        ).join(
            lf_full.filter(pl.col(periodName) == period).select(
                pl.col(metricToPlot).sum().alias("totalPeriod")
            ),
            how="cross",
        )
        metrics = metrics_lf.collect(engine="streaming")

        if metrics.height > 0:
            totalShown = metrics["totalShown"][0]
            totalPeriod = metrics["totalPeriod"][0]
            if totalPeriod != 0:
                percentShown = round(totalShown / totalPeriod * 100)

    fig.add_annotation(
        text=f"{percentShown}%",
        showarrow=True,
        arrowcolor="black",
        arrowhead=2,
        arrowsize=1,
        arrowwidth=2,
        x=1,
        y=1,
        ax=0,
        ay=-40,
        xref="paper",
        yref="paper",
        axref="pixel",
        ayref="pixel",
        align="center",
        yshift=0,
        xshift=0,
    )
    return fig


def add_values_to_data_column_on_right(
    figure,
    df,
    dfDataColMetrics,
    dfCumSum,
    value_cols,
    colName,
    count,
    chartDict,
    categories,
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    countColumn = namingParams["countColumn"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    metricsToShowInDataColumn = namingParams["metricsToShowInDataColumn"]
    dataColumnMetricOffset = configParams[namingParams["dataColumnMetricOffset"]]
    numberOfColumns = len(categories)
    xShift = get_x_shift_for_data_column(numberOfColumns, chartDict, "row")
    df_lazy = ensure_lazyframe(df)
    metrics_lazy = ensure_lazyframe(dfDataColMetrics)
    cumsum_lazy = ensure_lazyframe(dfCumSum)
    metric_columns, _ = get_schema_and_column_names(metrics_lazy)
    if not metric_columns:
        return figure
    metric_label_column = metric_columns[0]

    for metric_index, element in enumerate(chartDict[metricsToShowInDataColumn]):
        col_df = (
            metrics_lazy.filter(pl.col(metric_label_column) == element)
            .select(pl.col(colName))
            .collect(engine="streaming")
        )
        columnValue = col_df[colName][0] if col_df.height else 0
        if metric_index > 0:
            xShift = xShift + dataColumnMetricOffset
        if columnValue == 0:
            columnValue = ""
        else:
            # columnValue=int(round(columnValue,1))
            try:
                columnValue = millify(columnValue, 1)
            except Exception as e:
                logging.exception(e)
                _log_debug("metric formatting error:", e)
                columnValue = ""
            if "%" in element:
                columnValue = columnValue + "%"
        base = df_lazy.select(pl.col(colName).tail(2)).collect(engine="streaming")[
            colName
        ][0]
        if count == 0:
            yValue = base * 0.5
        else:
            colBelowName = value_cols[count - 1]
            below_last = (
                cumsum_lazy.select(pl.col(colBelowName).last())
                .collect(engine="streaming")
                .item()
            )
            yValue = base * 0.5 + below_last
        figure.add_annotation(
            text=str(columnValue),
            showarrow=False,
            align="center",
            yshift=0,
            y=yValue,
            ax=1,
            x=1,
            xref="paper",
            xshift=xShift,
            hovertext=colName,
        )
    return figure


def get_text_template(chartDict):
    namingParams = get_naming_params()
    IBCSdecimalName = namingParams["IBCSdecimalName"]
    roundValue = 0
    if IBCSdecimalName in chartDict and chartDict[IBCSdecimalName] >= 0:
        roundValue = chartDict[IBCSdecimalName]
    texttemplate = None
    textformat = None
    if roundValue == 1:
        texttemplate = " %{text:,.1f}"
        textformat = "{:,.1f}"
    elif roundValue == 2:
        texttemplate = " %{text:,.2f}"
        textformat = "{:,.2f}"
    elif roundValue == 2:
        texttemplate = " %{text:,.3f}"
        textformat = "{:,.3f}"
    return texttemplate, textformat


def get_x_axis_total(dfCopy, totalYaxisNumber, chartDict):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    multipliedMetric = namingParams["multipliedMetric"]
    monetaryLocalCurrencyName = namingParams["monetaryLocalCurrencyName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    lf = ensure_lazyframe(dfCopy)
    lf = lf.with_columns(
        (pl.col(chartDict[xAxisMetric]) * pl.col(chartDict[yAxisMetric])).alias(
            chartDict[multipliedMetric]
        )
    )
    metrics = (
        lf.select(
            pl.col(chartDict[multipliedMetric]).sum().alias("_area"),
            pl.col(chartDict[xAxisMetric]).sum().alias("_x"),
        )
        .collect(engine="streaming")
        .row(0)
    )
    totalAreaNumber = int(round(metrics[0], 0))
    if chartDict[xAxisMetric] in [monetaryLocalCurrencyName, volumeName, unitsName]:
        totalXaxisNumber = int(round(metrics[1], 0))
    else:
        totalXaxisNumber = totalAreaNumber / totalYaxisNumber
    if chartDict[xAxisMetric] in percentMetricsArray:
        totalXaxisNumber = totalXaxisNumber * 100
    totalXaxisNumber = round(totalXaxisNumber, 1)
    totalArea = millify(totalAreaNumber, 1)
    totalXaxis = millify(totalXaxisNumber, 1)
    return totalXaxis, totalArea, totalXaxisNumber, totalAreaNumber


def get_y_axis_total(df, chartDict, value_cols, width_col):
    namingParams = get_naming_params()
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    marginInPercentTotalName = namingParams["marginInPercentTotalName"]
    marginInPercentOfNetSalesTotalName = namingParams[
        "marginInPercentOfNetSalesTotalName"
    ]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    pricePerUnitTotalName = namingParams["pricePerUnitTotalName"]
    pricePerVolumeTotalName = namingParams["pricePerVolumeTotalName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    pricePerUnitNetDiscountTotalName = namingParams["pricePerUnitNetDiscountTotalName"]
    discountInPercentNameTotal = namingParams["discountInPercentNameTotalName"]
    discountInPercentName = namingParams["discountInPercentName"]
    pricePerVolumeNetDiscountTotalName = namingParams[
        "pricePerVolumeNetDiscountTotalName"
    ]
    showAverageValueName = namingParams["showAverageValueName"]
    valueName = namingParams["valueName"]
    if marginInPercentName in value_cols:
        totalYaxis = str(round(chartDict[marginInPercentTotalName], 1)) + "%"
        totalYaxisNumber = round(chartDict[marginInPercentTotalName], 1)
    elif marginInPercentOfNetSalesName in value_cols:
        totalYaxis = str(round(chartDict[marginInPercentOfNetSalesTotalName], 1)) + "%"
        totalYaxisNumber = round(chartDict[marginInPercentOfNetSalesTotalName], 1)
    elif pricePerUnitName in value_cols:
        totalYaxis = str(round(chartDict[pricePerUnitTotalName], 1))
        totalYaxisNumber = round(chartDict[pricePerUnitTotalName], 1)
    elif pricePerVolumeName in value_cols:
        totalYaxis = str(round(chartDict[pricePerVolumeTotalName], 1))
        totalYaxisNumber = round(chartDict[pricePerVolumeTotalName], 1)
    elif pricePerUnitNetDiscountName in value_cols:
        totalYaxis = str(round(chartDict[pricePerUnitNetDiscountTotalName], 1))
        totalYaxisNumber = round(chartDict[pricePerUnitNetDiscountTotalName], 1)
    elif pricePerVolumeNetDiscountName in value_cols:
        totalYaxis = str(round(chartDict[pricePerVolumeNetDiscountTotalName], 1))
        totalYaxisNumber = round(chartDict[pricePerVolumeNetDiscountTotalName], 1)
    elif discountInPercentName in value_cols:
        totalYaxis = str(round(chartDict[discountInPercentNameTotal], 1)) + "%"
        totalYaxisNumber = round(chartDict[discountInPercentNameTotal], 1)
    elif width_col:
        lf = ensure_lazyframe(df)
        total_df = lf.select(pl.col(width_col).sum().alias("__tot")).collect(
            engine="streaming"
        )
        total = total_df["__tot"][0] if total_df.height else 0
        if total is None or (isinstance(total, float) and math.isnan(total)):
            total = 0
        totalYaxis = int(round(total, 0))
        totalYaxisNumber = totalYaxis
        totalYaxis = millify(totalYaxis, 1)
    else:
        lf = ensure_lazyframe(df)
        if showAverageValueName in chartDict and chartDict[showAverageValueName]:
            total_df = lf.select(
                pl.col(valueName).slice(1).sum().alias("__tot")
            ).collect(engine="streaming")
        else:
            total_df = lf.select(pl.col(valueName).sum().alias("__tot")).collect(
                engine="streaming"
            )
        total = total_df["__tot"][0] if total_df.height else 0
        if total is None or (isinstance(total, float) and math.isnan(total)):
            total = 0
        totalYaxis = int(round(total, 0))
        totalYaxisNumber = totalYaxis
        totalYaxis = millify(totalYaxis, 1)
    return totalYaxis, totalYaxisNumber


def split_main_and_data_column_dataframe(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Split the main dataframe from data-column metrics and counts."""

    namingParams = get_naming_params()
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    numberOfMetricsInDataColumn = namingParams["numberOfMetricsInDataColumn"]

    df = ensure_polars_df(df)

    if showMetricsInDataColumn in chartDict and chartDict[showMetricsInDataColumn]:
        numberOfMetricsInDataColumn = chartDict[numberOfMetricsInDataColumn]

        # remove the final total row
        df = df.head(df.height - 1)

        dfDataColMetrics = duplicate_dataframe(df).tail(numberOfMetricsInDataColumn)

        # counts row precedes the metric rows
        dfCounts = df.slice(-numberOfMetricsInDataColumn - 1, 1)

        # drop counts row and metric rows from df
        df = df.head(df.height - 1)
        df = df.head(df.height - numberOfMetricsInDataColumn)
    else:
        numberOfMetricsInDataColumn = 0
        dfDataColMetrics = pl.DataFrame()
        if isinstance(df, pl.LazyFrame):
            dfCounts = collect_tail(df, 1, engine="streaming")
        else:
            dfCounts = df.tail(1).clone()
        df = df.head(df.height - 1)

    return (
        ensure_polars_df(df),
        ensure_polars_df(dfDataColMetrics),
        ensure_polars_df(dfCounts),
    )


def prepend_blank_row_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Prepend one "blank" (all-None) row in a lazy pipeline,
    ensuring it appears at the TOP of the final collected DataFrame.
    """
    # We need to define:
    #  1) a "row_order" column for our existing rows
    #  2) a "row_order" for the blank row that ensures it sorts first

    # First, add a zero-based row_count for the main LazyFrame
    # so each row gets row_order = 0, 1, 2, ...
    lf = ensure_lazyframe(lf)
    lf_with_order = (
        lf.with_row_index(name="row_order", offset=0)
        # cast index column so later schema checks are deterministic
        .with_columns(pl.col("row_order").cast(pl.Int64))
    )

    # Create a single-row DF with explicit schema
    columns, schema_dict = get_schema_and_column_names(lf_with_order)
    data = {"row_order": [-1]}
    final_schema: dict[str, pl.DataType] = {"row_order": pl.Int64}

    for col_name, dtype in schema_dict.items():
        if col_name == "row_order":
            continue
        data[col_name] = [None]
        final_schema[col_name] = dtype

    blank_df = pl.DataFrame(data=data, schema=final_schema)
    blank_lf = blank_df.lazy()

    # Now concat them: the blank row first, then the main data
    concatenated_lf = pl.concat([blank_lf, lf_with_order], how="vertical")

    # Finally, sort on "row_order" so that -1 is at the very top
    return concatenated_lf.sort("row_order")


def append_blank_row_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Append one "blank" (all-None) row at the BOTTOM of the final DataFrame.
    Guaranteed by sorting on row_order.
    """
    # Step 1: row_count -> cast to Int64
    lf = ensure_lazyframe(lf)
    lf_with_order = lf.with_row_index(name="row_order", offset=0).with_columns(
        pl.col("row_order").cast(pl.Int64)
    )

    columns, schema_dict = get_schema_and_column_names(lf_with_order)
    data = {}
    final_schema = {}
    for col_name, dtype in schema_dict.items():
        if col_name == "row_order":
            # Large sentinel so it ends up last
            data[col_name] = [99999999]
            final_schema[col_name] = pl.Int64
        else:
            data[col_name] = [None]
            final_schema[col_name] = dtype

    blank_df = pl.DataFrame(data=data, schema=final_schema).lazy()

    concatenated = pl.concat([lf_with_order, blank_df], how="vertical")
    return concatenated.sort("row_order")


def drop_all_null_rows_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Return ``lf`` without rows where every column is null."""

    columns, _ = get_schema_and_column_names(lf)
    if not columns:
        return lf

    all_null_expr = pl.all_horizontal([pl.col(c).is_null() for c in columns])
    return lf.filter(~all_null_expr)


def add_blank_column_for_data_column_annotations(
    lf: pl.LazyFrame, chosenChart: str, chartDict: dict
) -> tuple[pl.LazyFrame, dict]:
    """Add a null row when needed and record the action in ``chartDict``."""
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    showCAGR = namingParams["showCAGR"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    addBlankColumn = namingParams["addBlankColumn"]

    # Default
    chartDict[addBlankColumn] = notMetConditionValue

    # Example condition
    if (
        chosenChart in [stackedParetoChart]
        and showMetricsInDataColumn in chartDict
        and chartDict[showMetricsInDataColumn]
    ):
        chartDict[addBlankColumn] = metConditionValue
        lf = append_blank_row_lazy(lf)  # append

    if (
        chosenChart in [stackedColumnChart]
        and showCAGR in chartDict
        and chartDict[showCAGR]
    ):
        chartDict[addBlankColumn] = metConditionValue
        lf = append_blank_row_lazy(lf)  # append again

    if chosenChart in [stackedBarChart]:
        chartDict[addBlankColumn] = metConditionValue
        lf = prepend_blank_row_lazy(lf)  # prepend

    return lf, chartDict


def compute_positions(
    df: pl.LazyFrame, countName: str, bargap: float, makeColsThin: bool
):
    """
    Example function to add a 'count' column of 1, compute x positions
    (cumulative sums) and halfColumn, etc., all in lazy expressions.
    """

    # Create the count column
    df = df.with_columns(pl.lit(1).alias(countName))

    # Possibly use a separate column to store the final bar width
    width_expr = (pl.col(countName) - bargap).alias("width_col")
    # x expression => cumsum shifted by 1 to replicate the
    # np.cumsum([0] + list(df[countName][:-1])) logic
    x_expr = pl.col(countName).cum_sum().shift(1).fill_null(0).alias("x")

    # halfColumn => (countName / 2) + x
    half_expr = ((pl.col(countName) / 2) + pl.col("x")).alias("halfColumn")

    # Possibly make columns thinner if needed
    if makeColsThin:
        # Example: multiply width_col by 0.5 if you want them thinner
        width_expr = ((pl.col(countName) - bargap) * 0.5).alias("width_col")

    # Return a new lazy frame with these columns
    df = df.with_columns([width_expr])
    df = df.with_columns([x_expr])
    df = df.with_columns([half_expr])
    return df


def apply_marker_styles(
    df: pl.LazyFrame, chartDict: dict, namingParams: dict, color: str, count: int
):
    """
    Example helper to set markerLineColor, markerColor, textFontColor conditionally.
    """
    markerLineColorKey = namingParams["markerLineColor"]
    markerColorKey = namingParams["markerColor"]
    textFontColorKey = namingParams["textFontColor"]
    periodName = namingParams["periodName"]
    plName = namingParams["plName"]

    # Default all lines to 'white'
    df = df.with_columns(pl.lit("white").alias(markerLineColorKey))

    # If ``periodName`` is present set the line colour to black when its value
    # contains ``plName``.
    df = df.with_columns(
        pl.when(
            (pl.col(periodName).is_not_null())
            & (pl.col(periodName).str.contains(plName))
        )
        .then(pl.lit("black"))
        .otherwise(pl.col(markerLineColorKey))
        .alias(markerLineColorKey)
    )

    # Default marker color
    df = df.with_columns(pl.lit(color).alias(markerColorKey))

    # textFontColor can default to something if needed:
    df = df.with_columns(pl.lit("white").alias(textFontColorKey))

    # If count == 0 => override color with white where line is black
    if count == 0:
        df = df.with_columns(
            [
                pl.when(pl.col(markerLineColorKey) == "black")
                .then(pl.lit("white"))
                .otherwise(pl.col(markerColorKey))
                .alias(markerColorKey),
                pl.when(pl.col(markerLineColorKey) == "black")
                .then(pl.lit("black"))
                .otherwise(pl.col(textFontColorKey))
                .alias(textFontColorKey),
            ]
        )

    return df


def compute_half_column(
    df_lazy: pl.DataFrame | pl.LazyFrame | Any,
    label_col: str | None = None,
) -> pl.LazyFrame:
    """Return bar midpoints lazily with the associated label column."""

    lf = ensure_lazyframe(df_lazy)
    namingParams = get_naming_params()
    countName = namingParams["countName"]
    label_col = label_col or namingParams["periodName"]

    if isinstance(lf, pl.DataFrame):
        columns, _ = get_schema_and_column_names(lf)
    else:
        columns = lf.collect_schema().names()
    if label_col not in columns:
        label_col = columns[0]

    x_expr = pl.col(countName).cum_sum().shift(1).fill_null(0)
    half_expr = (pl.col(countName) / 2 + x_expr).alias("halfColumn")

    return lf.with_columns(half_expr).select(pl.col(label_col), pl.col("halfColumn"))


def get_marimekko_positions(
    df_lazy: pl.DataFrame | pl.LazyFrame | Any,
    count_name: str,
    width_col: str | int | float = 1,
) -> pl.LazyFrame:
    """Return cumulative width positions for a marimekko chart."""

    lf = ensure_lazyframe(df_lazy)
    if not isinstance(lf, (pl.DataFrame, pl.LazyFrame)):
        lf = pl.DataFrame(lf).lazy()
    elif isinstance(lf, pl.DataFrame):
        lf = lf.lazy()

    lf = lf.with_columns(pl.lit(1).alias(count_name))
    width_expr = pl.col(width_col) if isinstance(width_col, str) else pl.lit(width_col)
    lf = lf.with_columns(width_expr.cum_sum().shift(1).fill_null(0).alias("x"))
    lf = lf.with_columns((width_expr / 2 + pl.col("x")).alias("halfColumn"))
    return lf


def calculate_marimekko_positions(
    df_lazy: pl.DataFrame | pl.LazyFrame,
    count_name: str,
    width_col: str | int | float = 1,
) -> pl.LazyFrame:
    """Return marimekko width, x, half-column and tickval as a LazyFrame.

    The first column of the returned frame matches the first column of the
    input dataset.
    """

    lf = get_marimekko_positions(df_lazy, count_name, width_col)
    columns, _ = get_schema_and_column_names(df_lazy)
    first_col = columns[0] if columns else None

    select_expr: list[pl.Expr] = []
    added: set[str] = set()

    if first_col is not None:
        select_expr.append(pl.col(first_col))
        added.add(first_col)

    if isinstance(width_col, str) and width_col not in added:
        select_expr.append(pl.col(width_col))
        added.add(width_col)

    for name in ("x", "halfColumn"):
        if name not in added:
            select_expr.append(pl.col(name))
            added.add(name)

    select_expr.append((pl.col("x") + pl.col(width_col) / 2).alias("tickval"))

    return lf.select(*select_expr)


def add_total_annotations_for_marimekko(
    figure,
    category: str,
    halfColumn_lazy: pl.LazyFrame | pl.DataFrame,
    width_lazy: pl.LazyFrame | pl.DataFrame,
    chartDict: dict,
    row: int,
    col: int,
    category_col: str,
    width_col: str,  # or your namingParams["valueName"]    # or whatever col in halfColumn_lazy
):
    """Add marimekko column totals as annotations.

    LazyFrame inputs are collected with ``engine="streaming"`` for efficiency.

    Parameters
    ----------
    figure:
        Plotly figure to annotate.
    category:
        Category value to process.
    halfColumn_lazy:
        Polars ``LazyFrame`` with ``[category_col, half_val]`` used for the y
        positions.
    width_lazy:
        Polars ``LazyFrame`` with ``[category_col, width_col]`` containing the
        width values.
    chartDict:
        Chart configuration dictionary.
    row, col:
        Subplot position of the annotation.
    category_col:
        Name of the category column in the lazyframes.
    width_col:
        Column name with the width values.
    """
    namingParams = get_naming_params()
    # Always use ``halfColumn`` for the midpoint column
    half_val_col = "halfColumn"

    width_lf = ensure_lazyframe(width_lazy)
    half_lf = ensure_lazyframe(halfColumn_lazy)

    metrics_lf = (
        width_lf.group_by(category_col)
        .agg(pl.col(width_col).sum().alias("width_cat"))
        .join(
            half_lf.group_by(category_col).agg(
                pl.col(half_val_col).max().alias("half_val")
            ),
            on=category_col,
            how="full",
        )
        .filter(pl.col(category_col) == category)
        .join(
            width_lf.select(pl.col(width_col).sum().alias("total_width")),
            how="cross",
        )
        .select("total_width", "width_cat", "half_val")
    )

    metrics = metrics_lf.collect(engine="streaming")

    if metrics.height == 0:
        metrics = pl.DataFrame(
            {"total_width": [0.0], "width_cat": [0.0], "half_val": [0.0]}
        )

    check_collect("CAA", "marimekko_metrics", metrics)

    total_width = metrics["total_width"][0]
    width_for_this_category = metrics["width_cat"][0]
    half_val = metrics["half_val"][0] or 0.0

    if chartDict.get(
        namingParams["plotSmallMultiplesOtherCharts"]
    ) and not is_readable_mekko_row(width_for_this_category, total_width):
        return figure

    # replicate your math with one decimal after applying the value prefix
    value_prefix_name = namingParams["valuePrefixName"]
    mill_dict = {
        "t": 1_000_000_000_000,
        "b": 1_000_000_000,
        "m": 1_000_000,
        "k": 1_000,
        "": 1,
    }
    prefix = chartDict.get(value_prefix_name, "")
    divisor = mill_dict.get(prefix, 1)
    scaled_value = (width_for_this_category or 0.0) / divisor
    columnTotalValue = f"{scaled_value:.1f}"
    if total_width != 0:
        col_percent = int(round(width_for_this_category / total_width * 100, 0))
    else:
        col_percent = 0

    col_percent_str = f" ({millify(col_percent, 0)}%)"
    columnTotal = f"{columnTotalValue}{col_percent_str}"

    # 4) add annotation
    yshift = 0
    xshift = 40
    x = 1
    ax = x
    yref = "y"
    xref = "x"
    axref = "x"

    annotation_kwargs = {}
    if row is not None and col is not None:
        annotation_kwargs = {"row": row, "col": col}
    figure.add_annotation(
        text=columnTotal,
        showarrow=False,
        align="center",
        yshift=yshift,
        xshift=xshift,
        ax=ax,
        x=x,
        yref=yref,
        ay=half_val,
        y=half_val,
        xref=xref,
        axref=axref,
        **annotation_kwargs,
    )
    return figure


def add_total_annotations_for_barmekko(
    figure: go.Figure,
    df_lazy: pl.LazyFrame,
    category: str,
    halfColumn_lazy: pl.LazyFrame,
    width_lazy: pl.LazyFrame,
    chartDict: dict,
    row: int,
    col: int,
) -> go.Figure:
    """Add totals for a single barmekko column using lazy Polars."""

    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    multipliedMetric = namingParams["multipliedMetric"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]

    colorDict = get_color_dictionary(chartDict)

    df_lf = ensure_lazyframe(df_lazy)
    half_lf = ensure_lazyframe(halfColumn_lazy)
    width_lf = ensure_lazyframe(width_lazy)

    columns, _ = get_schema_and_column_names(df_lf)
    cat_col = columns[0]

    mult_expr = pl.col(chartDict[xAxisMetric]) * pl.col(chartDict[yAxisMetric])

    filtered_lf = (
        df_lf.join(half_lf, on=cat_col, how="left")
        .join(width_lf, on=cat_col, how="left")
        .filter(pl.col(cat_col) == category)
    )

    totals_lf = filtered_lf.select(
        pl.col(chartDict[xAxisMetric]).sum().alias("totalXaxisNumber"),
        pl.col(chartDict[yAxisMetric]).first().alias("totalYaxisNumber"),
        mult_expr.sum().alias("totalAreaNumber"),
        pl.col("halfColumn").first().alias("half_val"),
    ).join(
        df_lf.select(
            pl.col(chartDict[xAxisMetric]).max().alias("x_max"),
            pl.col(chartDict[xAxisMetric]).sum().alias("globalXaxisNumber"),
            mult_expr.max().alias("area_max"),
        ),
        how="cross",
    )

    metrics = totals_lf.collect(engine="streaming")
    check_collect("BAA", "barmekko_metrics", metrics.head())

    if metrics.height == 0:
        totalXaxisNumber = totalYaxisNumber = totalAreaNumber = 0
        half_val = x_max = globalXaxisNumber = area_max = 0
    else:
        totalXaxisNumber = metrics.get_column("totalXaxisNumber")[0]
        totalYaxisNumber = metrics.get_column("totalYaxisNumber")[0]
        totalAreaNumber = metrics.get_column("totalAreaNumber")[0]
        half_val = metrics.get_column("half_val")[0]
        x_max = metrics.get_column("x_max")[0]
        globalXaxisNumber = metrics.get_column("globalXaxisNumber")[0]
        area_max = metrics.get_column("area_max")[0]

    if chartDict.get(plotSmallMultiplesKey) and not is_readable_mekko_row(
        totalXaxisNumber, globalXaxisNumber
    ):
        return figure

    if chartDict[xAxisMetric] in percentMetricsArray:
        columnTotal = round(totalXaxisNumber * 100, 1)
    else:
        _, chartDict, _ = get_number_prefix(
            pl.LazyFrame({"val": [x_max]}),
            "val",
            chartDict,
            None,
            chartDict[xAxisMetric],
        )
        columnTotal = int(round(totalXaxisNumber, 0))
        columnTotal = divide_by_value_prefix(
            columnTotal, chartDict, chartDict[xAxisMetric]
        )

    _, chartDict, _ = get_number_prefix(
        pl.LazyFrame({"val": [area_max]}),
        "val",
        chartDict,
        None,
        chartDict[multipliedMetric],
    )
    areaTotal = int(round(totalAreaNumber, 0))
    areaTotal = divide_by_value_prefix(
        areaTotal, chartDict, chartDict[multipliedMetric]
    )

    figure.add_annotation(
        text=areaTotal,
        font=dict(color=colorDict["whiteColor"]),
        showarrow=False,
        align="center",
        y=half_val,
        yshift=0,
        yref="y",
        ay="y",
        x=totalYaxisNumber * 0.5,
        xref="x",
        xshift=0,
        ax="x",
        axref="x",
        row=row,
        col=col,
    )

    xshift = 0
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        xshift = 12

    figure.add_annotation(
        text=columnTotal,
        font=dict(color=colorDict["whiteColor"]),
        showarrow=False,
        align="right",
        y=half_val,
        yshift=0,
        yref="y",
        ay="y",
        x=0,
        xref="x domain",
        xshift=xshift,
        ax="x",
        axref="x",
        row=row,
        col=col,
    )
    return figure


def add_total_annotations(
    figure,
    chartDict,
    categories,  # list of category values
    halfColumn_lazy: pl.LazyFrame,
    width_lazy: pl.LazyFrame,
    df_lazy: pl.LazyFrame,  # if subcalls need the entire dataset
    row,
    col,
):
    """
    A Polars-lazy refactor of your original function.

    figure      : Plotly (or other) figure object
    chartDict   : dict with info about chart type, etc.
    categories  : list of category names/values to loop over
    halfColumn_lazy : LazyFrame containing [Category, HalfVal]
    width_lazy  : LazyFrame containing [Category, WidthVal (or your actual valueName)]
    df_lazy     : The entire lazy dataset if subcalls need it
    row, col    : subplot positioning
    """

    namingParams = get_naming_params()
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    chosenChartKey = namingParams["chosenChart"]  # "chosenChart"
    valuePrefixName = namingParams["valuePrefixName"]
    metricsToPlot = namingParams["metricsToPlot"]
    valueName = namingParams["valueName"]  # e.g. "WidthVal"
    periodName = namingParams["periodName"]

    chosenChart = chartDict[chosenChartKey]
    # Default column names for annotations
    valueColumn = valueName
    columns, schema = get_schema_and_column_names(df_lazy)
    for category in categories:
        if category != "":
            if chosenChart == marimekkoChart:
                categoryColumn = columns[0]

                figure = add_total_annotations_for_marimekko(
                    figure=figure,
                    category=category,
                    halfColumn_lazy=ensure_lazyframe(halfColumn_lazy),
                    width_lazy=ensure_lazyframe(width_lazy),
                    chartDict=chartDict,
                    row=row,
                    col=col,
                    category_col=categoryColumn,
                    width_col=valueColumn,
                )
            elif chosenChart == barmekkoChart:
                figure = add_total_annotations_for_barmekko(
                    figure=figure,
                    df_lazy=ensure_lazyframe(df_lazy),
                    category=category,
                    halfColumn_lazy=ensure_lazyframe(halfColumn_lazy),
                    width_lazy=ensure_lazyframe(width_lazy),
                    chartDict=chartDict,
                    row=row,
                    col=col,
                )
            elif chosenChart == stackedParetoChart:
                figure = add_total_annotations_for_stacked_pareto(
                    figure=figure,
                    category=category,
                    halfColumn_lazy=halfColumn_lazy,
                    width_lazy=width_lazy,
                    row=row,
                    col=col,
                )
            elif chosenChart == stackedColumnChart:
                categoryColumn = periodName
                figure, chartDict = add_total_annotations_for_stacked_column(
                    figure=figure,
                    category=category,
                    halfColumn_lazy=halfColumn_lazy,
                    width_lazy=width_lazy,
                    chartDict=chartDict,
                    category_col=categoryColumn,
                    width_col=valueColumn,
                    row=row,
                    col=col,
                )
            elif chosenChart == stackedBarChart:
                figure = add_total_annotations_for_stacked_bar(
                    figure=figure,
                    category=category,
                    halfColumn_lazy=halfColumn_lazy,
                    width_lazy=width_lazy,
                    chartDict=chartDict,
                    row=row,
                    col=col,
                )
    return figure, chartDict


def add_total_annotations_for_stacked_pareto(
    figure,
    category,
    halfColumn=None,
    width=None,
    row=None,
    col=None,
    halfColumn_lazy=None,
    width_lazy=None,
):
    namingParams = get_naming_params()
    if halfColumn is None and isinstance(halfColumn_lazy, list):
        halfColumn = {str(category): halfColumn_lazy[0] if halfColumn_lazy else 0}
    if halfColumn is None and halfColumn_lazy is not None:
        half_frame = ensure_lazyframe(halfColumn_lazy).collect()
        half_cols, _ = get_schema_and_column_names(half_frame)
        if len(half_cols) >= 2:
            halfColumn = {
                str(row[half_cols[0]]): row[half_cols[1]]
                for row in half_frame.iter_rows(named=True)
            }
    if width is None and width_lazy is not None:
        width_frame = ensure_lazyframe(width_lazy).collect()
        width_cols, _ = get_schema_and_column_names(width_frame)
        if len(width_cols) >= 2:
            width = {
                str(row[width_cols[0]]): row[width_cols[1]]
                for row in width_frame.iter_rows(named=True)
            }
    if isinstance(halfColumn, list):
        halfColumn = {
            str(item): halfColumn[index]
            for index, item in enumerate(category if isinstance(category, list) else [])
        }
    halfColumn = halfColumn or {}
    width = width or {}
    width_value = width.get(category, width.get(str(category), 0))
    half_value = halfColumn.get(category, halfColumn.get(str(category), 0))
    columnTotal = int(round(float(width_value or 0), 0))
    columnTotal = millify(columnTotal, 1)
    yshift = +0
    y = 1
    ay = 1
    yref = "paper"
    xref = "x"
    axref = "x"
    figure.add_annotation(
        text=columnTotal,
        showarrow=False,
        align="center",
        yshift=yshift,
        ay=ay,
        y=y,
        yref=yref,
        ax=half_value,
        x=half_value,
        xref=xref,
        axref=axref,
        row=row,
        col=col,
    )
    return figure


def set_stacked_pareto_params_and_add_trace(
    figure, subplot, dfCopy, dfCountsCopy, colName, color, chartDict, categories
):
    """Return bar parameters and updated figure for stacked pareto charts."""

    namingParams = get_naming_params()
    countName = namingParams["countName"]
    showLegend = namingParams["showLegend"]
    showBoth = namingParams["showBoth"]
    labelName = namingParams["labelName"]
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    showLegendInBars = namingParams["showLegendInBars"]
    workColumn = namingParams["workColumn"]
    countByColumn = namingParams["countByColumn"]

    orientation = "v"
    bargap = 0.1
    maxLabelLength = 20

    lf = ensure_lazyframe(dfCopy).with_columns(pl.lit(1).alias(countName))
    lf = lf.with_columns(
        [
            (pl.col(countName) - bargap).alias("__width"),
            pl.col(countName).shift(1).fill_null(0).cum_sum().alias("__x"),
        ]
    )
    lf = lf.with_columns((pl.col(countName) / 2 + pl.col("__x")).alias("__half"))

    lf, chartDict = millify_dataframe(lf, colName, None, labelName, chartDict)

    dfCounts_lf = ensure_lazyframe(dfCountsCopy).with_columns(
        pl.col(colName).cast(pl.Int64)
    )
    dfCounts_lf, chartDict = millify_dataframe(
        dfCounts_lf, colName, None, workColumn, chartDict
    )
    consts_lf = dfCounts_lf.select(
        pl.col(workColumn).first().alias("__count_val"),
        pl.len().alias("__cnt"),
    )
    lf = lf.join(consts_lf, how="cross")

    append_count_label = str(colName) == str(chartDict.get(countByColumn, ""))
    lf = lf.with_columns(
        pl.when(pl.col("__cnt") == 1)
        .then(
            pl.when(pl.lit(append_count_label))
            .then(
                pl.concat_str(
                    [
                        pl.col(labelName),
                        pl.lit("<BR>("),
                        pl.col("__count_val"),
                        pl.lit(")"),
                    ]
                )
            )
            .otherwise(pl.col(labelName))
        )
        .otherwise(pl.col(labelName))
        .alias(labelName)
    ).drop(["__count_val", "__cnt"])

    collected = lf.select(
        [
            pl.col(labelName),
            pl.col(colName),
            pl.col(countName),
            pl.col("__width"),
            pl.col("__x"),
            pl.col("__half"),
        ]
    ).collect(engine="streaming")

    value_list = collected[colName].to_list()
    text_list = collected[labelName].to_list()
    if chartDict.get(namingParams["aggregateUniquesByDimension"]):
        text_list = [
            text if _is_readable_stacked_pareto_segment(value) else ""
            for text, value in zip(text_list, value_list)
        ]
    if chartDict[showLegend] in [showBoth, showLegendInBars]:
        text_list = [f"{colName[:maxLabelLength]} {t}" if t else "" for t in text_list]

    x = collected["__x"].to_list()
    width = collected["__width"].to_list()
    halfColumn = collected["__half"].to_list()
    tickvals = [xi + ci / 2 for xi, ci in zip(x, collected[countName].to_list())]
    ticktext = ["%s" % (l) for l in zip(categories)]
    tickrange = [0, collected[countName].sum() - bargap]

    tickformat = ""
    rangeArray = None
    visible = False
    showticklabels = False
    textposition = "auto"
    textfontcolor = "white"
    barmode = "relative"
    insidetextanchor = "middle"

    figure.add_trace(
        go.Bar(
            name=colName,
            x=x,
            y=value_list,
            width=width,
            marker_color=color,
            text=text_list,
            textposition=textposition,
            insidetextanchor=insidetextanchor,
            textangle=0,
            textfont_color=textfontcolor,
            hovertext=text_list,
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
        maxLabelLength,
        chartDict,
    )


def add_first_row_annotations_for_stacked_pareto(
    figure, chartDict, numberOfColumns, row, col
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    dataColumnMetricOffset = configParams[namingParams["dataColumnMetricOffset"]]
    metricsToShowInDataColumnKey = namingParams["metricsToShowInDataColumn"]
    dataColMetricNameKey = namingParams["dataColMetricName"]
    averageTotalValueKey = namingParams["averageTotalValue"]
    yref = "paper"
    yshift = +0
    maxTitleLength = 15
    shiftChange = 180
    xShift = get_x_shift_for_data_column(numberOfColumns, chartDict, "title")
    xShift = xShift + 10
    count = 0
    for element in chartDict[metricsToShowInDataColumnKey]:
        if count > 0:
            dataColumnMetricOffset = dataColumnMetricOffset + 15
            xShift = xShift + dataColumnMetricOffset
        averageTotalValue = chartDict[averageTotalValueKey][element]
        dataColMetricTitle = chartDict[dataColMetricNameKey][element]
        # averageTotalValue=int(round(averageTotalValue,1))
        averageTotalValue = millify(averageTotalValue, 1)
        dataColMetricTitle = change_metric_if_cost_analysis(
            dataColMetricTitle, chartDict
        )
        if "%" in element:
            averageTotalValue = averageTotalValue + "%"
        figure.add_annotation(
            text=dataColMetricTitle + "<br>" + averageTotalValue,
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
        count = count + 1
    return figure


def add_first_row_annotations_for_barmekko(
    df, figure, totalYaxisNumber, totalXaxisNumber, totalAreaNumber, chartDict, row, col
):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    discountInPercentName = namingParams["discountInPercentName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    multipliedMetric = namingParams["multipliedMetric"]
    valuePrefixDict = namingParams["valuePrefixDict"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    is_small_multiples = bool(chartDict.get(plotSmallMultiplesKey))
    if chartDict[yAxisMetric] in percentMetricsArray:
        totalYaxis = round(totalYaxisNumber, 1)
    elif chartDict[yAxisMetric] in priceMetricsArray:
        # Price metrics are never scaled to prefixes; use weighted average price.
        if totalXaxisNumber:
            totalYaxisNumber = totalAreaNumber / totalXaxisNumber
        totalYaxis = round(totalYaxisNumber, 1)
    else:
        totalYaxis = divide_by_value_prefix(
            totalYaxisNumber, chartDict, chartDict[yAxisMetric]
        )
    if chartDict[xAxisMetric] in percentMetricsArray:
        totalXaxis = round(totalXaxisNumber, 1)
    else:
        totalXaxis = divide_by_value_prefix(
            totalXaxisNumber, chartDict, chartDict[xAxisMetric]
        )
    if is_small_multiples and valuePrefixDict in chartDict:
        prefix_dict = chartDict[valuePrefixDict]
        multiplied_metric = chartDict.get(multipliedMetric)
        axis_metrics = {chartDict.get(xAxisMetric), chartDict.get(yAxisMetric)}
        area_sources = [
            metric
            for metric in prefix_dict
            if metric not in axis_metrics and metric != multiplied_metric
        ]
        if multiplied_metric and area_sources:
            prefix_dict[multiplied_metric] = prefix_dict[area_sources[-1]]
    totalArea = divide_by_value_prefix(
        totalAreaNumber, chartDict, chartDict[multipliedMetric]
    )
    totalYaxis, totalXaxis, totalArea = str(totalYaxis), str(totalXaxis), str(totalArea)
    if chartDict[yAxisMetric] in [marginInPercentName, marginInPercentOfNetSalesName]:
        totalYName = chartDict[yAxisMetric]
    elif chartDict[yAxisMetric] in [pricePerUnitName]:
        totalYName = chartDict[yAxisMetric]
    else:
        totalYName = chartDict[yAxisMetric]
    xAxisTitle = chartDict[xAxisMetric]
    totalAreaTitle = chartDict[multipliedMetric]
    totalYName = change_metric_if_cost_analysis(totalYName, chartDict)
    xAxisTitle = change_metric_if_cost_analysis(xAxisTitle, chartDict)
    totalAreaTitle = change_metric_if_cost_analysis(totalAreaTitle, chartDict)
    if is_small_multiples:
        figure.add_annotation(
            text="Total<br><b>" + totalArea + "</b>",
            showarrow=False,
            align="left",
            yshift=24,
            ay=1,
            y=1,
            yref="y domain",
            ax=0,
            x=0,
            xref="x domain",
            xanchor="left",
            xshift=0,
            row=row,
            col=col,
        )
        return figure

    yshift = 20
    xShiftA = 0
    xShiftB = 0
    xShiftC = -15
    if row:
        yshift = 217
        xShiftA = 0
        xShiftB = -10
        xShiftC = -80
    if is_small_multiples:
        # Anchor totals within each subplot domain for consistent placement.
        yshift = 8
        xShiftA = 0
        xShiftB = 0
        xShiftC = 0
    figure.add_annotation(
        text=totalYName + " (<b>" + totalYaxis + "</b>)",
        showarrow=False,
        align="center",
        yshift=yshift,
        ay=1,
        y=1,
        yref="y domain" if is_small_multiples else "paper",
        ax=1,
        x=1,
        xref="x domain" if is_small_multiples else "paper",
        xshift=xShiftA,
        row=row,
        col=col,
    )
    figure.add_annotation(
        text=totalAreaTitle + " (" + "<b>" + totalArea + "</b>)",
        showarrow=False,
        align="center",
        yshift=yshift,
        ay=1,
        y=1,
        yref="y domain" if is_small_multiples else "paper",
        ax=1,
        x=get_polars_value_at_index(
            ensure_lazyframe(df),
            chartDict[yAxisMetric],
            -1,
        )
        * 0.5,
        xref="x domain" if is_small_multiples else "x",
        xshift=xShiftB,
        row=row,
        col=col,
    )
    figure.add_annotation(
        text=xAxisTitle + " (" + "<b>" + totalXaxis + "</b>)",
        showarrow=False,
        align="center",
        yshift=yshift,
        ay=0,
        y=1,
        yref="y domain" if is_small_multiples else "paper",
        ax=1,
        x=0,
        xref="x domain",
        xshift=xShiftC,
        row=row,
        col=col,
    )
    return figure


def add_first_row_annotations(
    df,
    figure,
    chartDict,
    totalYaxis,
    totalXaxis,
    totalArea,
    numberOfColumns,
    count,
    row,
    col,
):
    """adding grand total to charts"""
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    chosenChart = namingParams["chosenChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    showCAGR = namingParams["showCAGR"]
    singleMetric = namingParams["singleMetric"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    metricsToPlot = namingParams["metricsToPlot"]
    singleMetric = namingParams["singleMetric"]
    synthesisPlot = namingParams["synthesisPlot"]
    chosenChart = chartDict[chosenChart]
    if chosenChart in [marimekkoChart]:
        if (
            chartDict[singleMetric]
            not in priceMetricsArray + percentMetricsArray + growthMetricArray
        ):
            figure = add_first_row_annotations_for_marimekko_and_stacked_bar(
                figure, totalYaxis, chartDict, row, col
            )
    elif chosenChart in [stackedBarChart]:
        if (
            chartDict[metricsToPlot][0]
            not in priceMetricsArray + percentMetricsArray + growthMetricArray
        ):
            figure = add_first_row_annotations_for_marimekko_and_stacked_bar(
                figure, totalYaxis, chartDict, row, col
            )
    elif chosenChart in [barmekkoChart]:
        figure = add_first_row_annotations_for_barmekko(
            df, figure, totalYaxis, totalXaxis, totalArea, chartDict, row, col
        )
    elif (
        chosenChart in [stackedParetoChart]
        and showMetricsInDataColumn in chartDict
        and chartDict[showMetricsInDataColumn]
    ):
        figure = add_first_row_annotations_for_stacked_pareto(
            figure, chartDict, numberOfColumns, row, col
        )
    elif (
        chosenChart in [stackedColumnChart]
        and synthesisPlot in chartDict
        and chartDict[synthesisPlot]
    ):
        figure = add_first_row_annotations_for_stacked_column_synplot(
            figure, chartDict, row, col
        )
    return figure


def add_first_row_annotations_for_stacked_column_synplot(figure, chartDict, row, col):
    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    chosenChartKey = namingParams["chosenChart"]
    singleMetric = namingParams["singleMetric"]
    metricsToPlot = namingParams["metricsToPlot"]
    columnTotalKey = namingParams["columnTotal"]
    chosenChart = chartDict[chosenChartKey]
    yref = "paper"
    yshift = +0
    xshift = +30
    totalYName = "Total<br>"
    totalYaxis = str(chartDict[columnTotalKey])
    figure.add_annotation(
        text=totalYName + "<b>" + totalYaxis + "</b>",
        showarrow=False,
        align="center",
        yshift=yshift,
        ay=1,
        y=1,
        yref=yref,
        ax=1,
        x=1,
        xref="x domain",
        xshift=xshift,
        row=row,
        col=col,
    )
    return figure


def get_polars_value_at_index(
    df_lazy: pl.DataFrame | pl.LazyFrame, col_name: str, index_val: int
):
    """
    Return a single scalar value from df_lazy[col_name] at
    row index index_val. Because Polars doesn't allow
    negative indexing or direct .iloc in lazy mode,
    we do minimal collects.

    If index_val >= 0, we do a slice(index_val, 1).
    If index_val == -1, we do tail(1).
    If index_val == -2, we do tail(2).head(1).
    etc.
    """
    if index_val >= 0:
        # slice(start, length)
        mini_df = (
            ensure_lazyframe(df_lazy)
            .slice(index_val, 1)
            .select(pl.col(col_name))
            .collect(engine="streaming")
        )
    else:
        # negative indexing approach:
        # e.g. -1 => tail(1)
        # e.g. -2 => tail(2).head(1)
        abs_val = abs(index_val)
        mini_df = collect_tail(
            ensure_lazyframe(df_lazy).select(pl.col(col_name)),
            abs_val,
            engine="streaming",
        )
        if abs_val > 1:
            mini_df = mini_df.head(1)

    # Collect only that small slice:
    check_collect("BAA", "collected", mini_df.head())
    if mini_df.height > 0:
        return mini_df[col_name][0]
    return 0


def add_first_row_annotations_for_marimekko_and_stacked_bar(
    figure, totalYaxisNumber, chartDict, row, col
):
    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    chosenChartKey = namingParams["chosenChart"]
    singleMetric = namingParams["singleMetric"]
    metricsToPlot = namingParams["metricsToPlot"]
    stackedBarChart = namingParams["stackedBarChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    chosenChart = chartDict[chosenChartKey]
    if chosenChart in [stackedBarChart]:
        metric = chartDict[metricsToPlot][0]
    else:
        metric = chartDict[singleMetric]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    is_small_multiples = bool(chartDict.get(plotSmallMultiplesKey))

    yref = "paper"
    yshift = +40
    xshift = +0
    if row and chosenChart in [stackedBarChart]:
        yshift = 210
        xshift = +550
    elif row:
        yshift = 310
        xshift = +35
    if is_small_multiples:
        # Keep totals aligned inside each subplot panel.
        yref = "y domain"
        yshift = 8
        xshift = 0
        if chosenChart in [stackedBarChart]:
            yshift = 20
    totalYName = "Total<br>"
    totalYaxis = divide_by_value_prefix(totalYaxisNumber, chartDict, metric)
    totalYaxis = str(totalYaxis)
    xref = "x domain"
    if chosenChart in [marimekkoChart]:
        xref = "x"
        xshift = 40
    if is_small_multiples:
        xref = "x domain"
        xshift = 0
    x = 1
    xanchor = "center"
    align = "center"
    ax = 1
    if is_small_multiples and chosenChart in [marimekkoChart]:
        x = 0
        ax = 0
        xanchor = "left"
        align = "left"
    figure.add_annotation(
        text=totalYName + "<b>" + totalYaxis + "</b>",
        showarrow=False,
        align=align,
        yshift=yshift,
        ay=1,
        y=1,
        yref=yref,
        ax=ax,
        x=x,
        xref=xref,
        xanchor=xanchor,
        xshift=xshift,
        row=row,
        col=col,
    )
    return figure


def add_total_annotations_for_stacked_column(
    figure,
    category: str,
    halfColumn_lazy: pl.LazyFrame,  # ex: columns ["Category", "HalfVal"]
    width_lazy: pl.LazyFrame,  # ex: columns ["Category", "WidthVal"]
    chartDict: dict,
    category_col: str,
    width_col: str,
    row: int,
    col: int,
    # Optionally define the relevant column names
):
    """
    Polars-lazy version of 'add_total_annotations_for_stacked_column'.

    In the original Pandas code:
      - 'width[category]' is replaced by a filter on 'width_lazy'
        for the matching category, then a small collect.
      - 'halfColumn[category]' likewise is a filter on 'halfColumn_lazy'.
      - 'dfAbsolute.max() / dfAbsolute[category]' (or .tail(1)) is replaced
        by minimal collects if 'dfAbsolute' is also Polars-lazy.
    """

    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    valuePrefixName = namingParams["valuePrefixName"]
    columnTotalKey = namingParams["columnTotal"]
    countNameKey = namingParams["countName"]

    # If we do NOT plot small multiples, proceed with annotation logic
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        # Case A: chartDict[plotValuesAsChoice] == 'absolute'
        #         => direct numeric from width for this category
        if chartDict[plotValuesAsChoice] == absolute:
            df_width_cat = (
                width_lazy.filter(pl.col(category_col) == category).select(
                    pl.col(width_col)
                )
            ).collect()
            check_collect("FAA", "df_width_cat", df_width_cat.head())
            if df_width_cat.height > 0:
                # single-column frame; extract scalar via Polars API
                wcat = df_width_cat.item()
            else:
                wcat = 0
            columnTotal = divide_by_value_prefix(wcat, chartDict, False)
            yref = "y"
            yValue = wcat
            yshift = 10
        # Case B: otherwise => handle 'dfAbsolute' from chartDict[absolute]
        else:
            dfAbsolute = chartDict[absolute]  # could be Polars lazy/eager or numeric

            # ~~~ Get the maxValue, replicate dfAbsolute.max().values[0] ~~~
            maxValue = 0
            if isinstance(dfAbsolute, pl.LazyFrame):
                df_max = dfAbsolute.select(pl.all().max()).collect()
                check_collect("GAA", "df_max", df_max)
                if df_max.height > 0:
                    idx = 1 if df_max.width > 1 else 0
                    maxValue = df_max.row(0)[idx]
                else:
                    maxValue = 0

            elif isinstance(dfAbsolute, pl.DataFrame):
                df_max = dfAbsolute.select(pl.all().max())
                check_collect("GAA", "df_max", df_max)
                if df_max.height > 0:
                    idx = 1 if df_max.width > 1 else 0
                    maxValue = df_max.row(0)[idx]
                else:
                    maxValue = 0

            elif isinstance(dfAbsolute, (float, int)):
                # It's already just a numeric
                maxValue = dfAbsolute

            else:
                maxValue = 0

            # replicate your get_number_prefix logic
            prefix, chartDict, decimals = get_number_prefix(
                maxValue, chartDict, None, False
            )

            # for stacked percentages, you used yValue=1, yref="paper"
            yValue = 1
            yref = "paper"
            yshift = 0

            # replicate logic to read "columnTotal" from dfAbsolute[category]
            if isinstance(dfAbsolute, pl.LazyFrame):
                # Attempt to get the row for 'category'
                df_abs_cat = dfAbsolute.filter(pl.col(category_col) == category)
                df_abs_cat_p = df_abs_cat.collect()
                check_collect("HAA", "df_abs_cat_p", df_abs_cat_p.head())
                if df_abs_cat_p.height > 0:
                    idx = 1 if df_abs_cat_p.width > 1 else 0
                    col_val = df_abs_cat_p.row(0)[idx]
                else:
                    # fallback to tail(1)
                    tail1 = dfAbsolute.tail(1).collect()
                    check_collect("LAA", "tail1", tail1.head())
                    if tail1.height > 0:
                        idx = 1 if tail1.width > 1 else 0
                        col_val = tail1.row(0)[idx]
                    else:
                        col_val = 0
                columnTotal = int(round(col_val, 0))

            elif isinstance(dfAbsolute, pl.DataFrame):
                df_abs_cat = dfAbsolute.filter(pl.col(category_col) == category)
                if df_abs_cat.height > 0:
                    idx = 1 if df_abs_cat.width > 1 else 0
                    col_val = df_abs_cat.row(0)[idx]
                else:
                    tail1 = dfAbsolute.tail(1)
                    if tail1.height > 0:
                        idx = 1 if tail1.width > 1 else 0
                        col_val = tail1.row(0)[idx]
                    else:
                        col_val = 0
                columnTotal = int(round(col_val, 0))

            elif isinstance(dfAbsolute, (float, int)):
                # If it's just a single numeric
                columnTotal = int(round(dfAbsolute, 0))

            else:
                columnTotal = 0

            # scale with your "divide_by_value_prefix" logic
            columnTotal = divide_by_value_prefix(columnTotal, chartDict, False)

        # store in chartDict
        chartDict[columnTotalKey] = columnTotal
        xref = "x"
        axref = "x"
        xShift = 0

        # replicate textformat if defined
        texttemplate, textformat = get_text_template(chartDict)
        if textformat:
            columnTotal = textformat.format(columnTotal)
        # ~~~ get halfColumn for this category ~~~
        df_half_cat = (
            halfColumn_lazy.filter(pl.col(category_col) == category).select(
                pl.col("halfColumn")
            )
        ).collect()
        check_collect("MAA", "df_half_cat", df_half_cat.head())
        if df_half_cat.height > 0:
            halfVal = df_half_cat.item()
        else:
            halfVal = 0

        # ~~~ add annotation ~~~
        figure.add_annotation(
            text=columnTotal,
            showarrow=False,
            align="center",
            yshift=yshift,
            yref=yref,
            y=yValue,
            ax=halfVal,
            x=halfVal,
            xref=xref,
            axref=axref,
            xshift=xShift,
            row=row,
            col=col,
        )

    return figure, chartDict


def add_total_annotations_for_stacked_bar(
    figure,
    category: str,
    halfColumn_lazy: pl.LazyFrame,
    width_lazy: pl.LazyFrame,
    chartDict: dict,
    row: int,
    col: int,
) -> go.Figure:
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    metricsToPlot = namingParams["metricsToPlot"]
    nanFillValue = namingParams["nanFillValue"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    width_lf = ensure_lazyframe(width_lazy)
    half_lf = ensure_lazyframe(halfColumn_lazy)
    half_cols, _ = get_schema_and_column_names(half_lf)
    if "halfColumn" not in half_cols:
        if isinstance(width_lf, pl.DataFrame):
            width_cols, _ = get_schema_and_column_names(width_lf)
        else:
            width_cols = width_lf.collect_schema().names()
        count_name = namingParams["countName"]
        period_name = namingParams["periodName"]
        if count_name not in width_cols:
            raise KeyError(f"Column '{count_name}' is required to compute 'halfColumn'")
        label_col = period_name if period_name in width_cols else width_cols[0]
        half_lf = compute_half_column(width_lf, label_col)
    columns, schema = get_schema_and_column_names(width_lf)
    wcat_df = (
        width_lf.filter(pl.col(columns[0]) == category)
        .select(pl.col(columns[1]))
        .collect(engine="streaming")
    )
    wcat = wcat_df.item() if wcat_df.height > 0 else 0
    width_sum_df = width_lf.select(pl.col(columns[1]).sum()).collect(engine="streaming")
    width_sum = width_sum_df.item() if width_sum_df.height > 0 else 0
    wcat_missing = wcat is None
    if wcat_missing:
        wcat = 0
    if width_sum is None:
        width_sum = 0

    checkIfNan = str(wcat)
    if not wcat_missing and checkIfNan not in ["Nan", "nan", np.nan]:
        notNan = True
        if 1 == 3 and wcat < 1:
            columnTotalValue = round(wcat, 2)
        else:
            if width_sum != 0:
                columnTotalValue = divide_by_value_prefix(wcat, chartDict, False)
            else:
                columnTotalValue = 0
        if width_sum != 0:
            columnTotalPercent = int(round(wcat / width_sum * 100, 0))
        else:
            columnTotalPercent = 0
        columnTotalPercent = millify(columnTotalPercent, 0) + "%"
        texttemplate, textformat = get_text_template(chartDict)
        if textformat:
            columnTotalValue = float(columnTotalValue)
            columnTotalValue = textformat.format(columnTotalValue)
    else:
        notNan = False
        columnTotalValue, columnTotalPercent = "", ""
    yshift = 0
    columns, schema = get_schema_and_column_names(half_lf)

    half_df = (
        half_lf.filter(pl.col(columns[0]) == category)
        .select(pl.col("halfColumn"))
        .collect(engine="streaming")
    )
    y = str(category)
    ay = y
    yref = "y"
    ayref = "y"
    if chartDict[plotValuesAsChoice] == absolute:
        x = wcat
        ax = x
        xref = "x"
        axref = "x"
        xshift = 45
    else:
        x = 1
        ax = x
        xref = "paper"
        axref = "x"
        xshift = 30
    if (
        chartDict[metricsToPlot][0]
        not in priceMetricsArray + percentMetricsArray + growthMetricArray
    ):
        columnTotal = str(columnTotalValue) + " (" + columnTotalPercent + ")"
        if "()" in columnTotal:
            columnTotal = ""
    elif chartDict[metricsToPlot][0] in percentMetricsArray + growthMetricArray:
        if str(wcat) not in ["Nan", "nan", np.nan]:
            try:
                if chartDict[metricsToPlot][0] in percentMetricsArray:
                    columnTotal = str(int(round(wcat, 0))) + "%"
                elif chartDict[metricsToPlot][0] in growthMetricArray:
                    columnTotal = str(int(wcat)) + "%"
            except Exception as e:
                logging.exception(e)
                _log_debug("metric formatting error:", e)
                columnTotal = ""
        xshift = 20
    else:
        if notNan:
            columnTotal = columnTotalValue
        else:
            columnTotal = ""
        xshift = 20
    if x < 0:
        xshift = -xshift
    figure.add_annotation(
        text=columnTotal,
        showarrow=False,
        align="center",
        y=y,
        ay=ay,
        yref=yref,
        ayref=ayref,
        yshift=yshift,
        x=x,
        ax=ax,
        xref=xref,
        axref=axref,
        xshift=xshift,
        row=row,
        col=col,
    )
    return figure


def add_legends_to_horizontal_waterflow(figure, df, chartDict, row, col):
    from modules.utilities.utils import get_row_count

    namingParams = get_naming_params()
    configParams = get_config_params()
    colorDict = get_color_dictionary(chartDict)
    font = configParams[namingParams["fontChoice"]]
    fontSize = configParams[namingParams["fontSizeText"]]
    deltaName = namingParams["deltaName"]
    acName = namingParams["acName"]
    fcName = namingParams["fcName"]
    labelName = namingParams["labelName"]
    align = "center"
    yShift = 0
    yref = "y"
    # Compute sums/last label via Polars to avoid pandas-style access
    lf = ensure_lazyframe(df)
    ac_sum_df = lf.select(pl.col(acName).sum().alias("__sum")).collect(
        engine="streaming"
    )
    ac_sum = ac_sum_df["__sum"][0] if ac_sum_df.height else 0
    y = (ac_sum or 0) * 0.5
    xref = "x"
    row_count = get_row_count(df)
    x = row_count - 1
    text = acName
    ax = x
    xShift = 25
    figure.add_annotation(
        text=text,
        showarrow=False,
        font=dict(
            size=fontSize,
            color=colorDict["blackColor"],
        ),
        align=align,
        yshift=yShift,
        yref=yref,
        y=y,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        hovertext=acName,
        row=row,
        col=col,
    )
    last_label_df = lf.select(pl.col(labelName).last().alias("__last")).collect(
        engine="streaming"
    )
    text = last_label_df["__last"][0] if last_label_df.height else None
    xShift = 0
    figure.add_annotation(
        text=text,
        showarrow=False,
        font=dict(
            size=fontSize,
            color=colorDict["whiteColor"],
        ),
        align=align,
        yshift=yShift,
        yref=yref,
        y=y,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        hovertext=text,
        row=row,
        col=col,
    )
    xShift = 25
    fc_sum_df = lf.select(pl.col(fcName).sum().alias("__sum")).collect(
        engine="streaming"
    )
    fc_sum = fc_sum_df["__sum"][0] if fc_sum_df.height else 0
    y = (fc_sum or 0) * 0.5 + (ac_sum or 0)
    figure.add_annotation(
        text=fcName,
        showarrow=False,
        font=dict(
            size=fontSize,
        ),
        align=align,
        yshift=yShift,
        yref=yref,
        y=y,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        hovertext=fcName,
        row=row,
        col=col,
    )
    fcTotal = divide_by_value_prefix(fc_sum or 0, chartDict, False)
    xShift = 1
    figure.add_annotation(
        text=fcTotal,
        showarrow=False,
        font=dict(
            size=fontSize,
        ),
        bgcolor=colorDict["whiteColor"],
        align=align,
        yshift=yShift,
        yref=yref,
        y=y,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        hovertext=fcName,
        row=row,
        col=col,
    )
    return figure


def add_legends_on_left(
    figure, df, dfCumSum, numberOfColumns, value_cols, colname, count, chartDict
):
    namingParams = get_naming_params()
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    chosenChart = namingParams["chosenChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    xShift = -53
    yShift = 0
    align = "center"
    df_lazy = ensure_lazyframe(df)
    cumsum_lazy = ensure_lazyframe(dfCumSum)
    first_val = (
        df_lazy.select(pl.col(colname).first()).collect(engine="streaming").item()
    )
    if (
        chartDict[chosenChart] in [stackedParetoChart]
        and chartDict.get(aggregateUniquesByDimension)
        and not _is_readable_stacked_pareto_segment(first_val)
    ):
        return figure
    yValue = first_val * 0.5
    if count != 0:
        below_val = (
            cumsum_lazy.select(pl.col(value_cols[count - 1]).first())
            .collect(engine="streaming")
            .item()
        )
        yValue += below_val
    ax = adjust_ax_by_number_of_columns(numberOfColumns, chartDict)
    x = ax
    xref = "paper"
    xAnchor = "auto"
    if chartDict[chosenChart] in [stackedParetoChart]:
        if chartDict.get(aggregateUniquesByDimension):
            left_edge_x = _stacked_column_plot_edge_x(figure, "left")
            if left_edge_x is not None:
                ax = left_edge_x
                x = left_edge_x
                xref = "x"
                xShift = -10
                xAnchor = "right"
                align = "right"
        else:
            xShift = 0
    if len(colname) > 14:
        firstpart = colname[:8]
        secondpart = colname[8:]
        secondpart = secondpart.replace(" ", " <BR>", 1)
        colname = firstpart + secondpart
    figure.add_annotation(
        text=colname,
        showarrow=False,
        align=align,
        yshift=yShift,
        y=yValue,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        xanchor=xAnchor,
        hovertext=colname,
    )
    return figure


def add_legends_on_top(
    figure: go.Figure,
    chosenChart: str,
    df: pl.DataFrame | pl.LazyFrame,
    dfCumSum: pl.DataFrame | pl.LazyFrame,
    value_cols: list[str],
    colname: str,
    count: int,
    chartDict: dict,
    row: int | None,
    col: int | None,
) -> go.Figure:
    """Add legend annotations above bars for stacked and Mekko charts."""

    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    showValuesAs = namingParams["showValuesAs"]
    absolute = namingParams["absolute"]
    marimekkoChart = namingParams["marimekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    align = "center"
    yShift = 22
    yref = "paper"
    y = 1

    df_lazy = ensure_lazyframe(df)
    df_cumsum_lazy = ensure_lazyframe(dfCumSum)
    if chosenChart in [stackedBarChart]:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            yShift = 195
        xref = "x"
        val_current = get_polars_value_at_index(df_lazy, colname, -1)
        half_val = val_current * 0.5 if val_current else 0
        if count == 0:
            x = half_val
        else:
            prev_val = get_polars_value_at_index(
                df_cumsum_lazy, value_cols[count - 1], -1
            )
            x = (prev_val or 0) + half_val
        ax = x
        xShift = 0
    elif chosenChart in [marimekkoChart]:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            if chartDict[numberOfPlottedSmallMultiplesKey] <= 4:
                yShift = 300
            else:
                yShift = 205
        else:
            # Place category labels just above the bottom totals for single Mekko charts.
            y = 0
            yShift = -15
        xref = "x"
        val_current = get_polars_value_at_index(df_lazy, colname, -1)
        half_val = val_current * 0.5 if val_current else 0
        if count == 0:
            x = half_val
        else:
            prev_val = get_polars_value_at_index(
                df_cumsum_lazy, value_cols[count - 1], -1
            )
            x = (prev_val or 0) + half_val
        ax = x
        xShift = 0
        xref = "x"
    if len(colname) > 14:
        colname = colname.replace(" ", " <BR>", 1)
    annotation_kwargs = {}
    if row is not None and col is not None:
        annotation_kwargs = {"row": row, "col": col}
    figure.add_annotation(
        text=colname,
        showarrow=False,
        align=align,
        yshift=yShift,
        yref=yref,
        y=y,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        hovertext=colname,
        **annotation_kwargs,
    )
    return figure


def add_legends_on_left_or_right(
    figure,
    df_lazy: pl.LazyFrame,  # Already Lazy
    dfCumSum_lazy: pl.LazyFrame,  # Already Lazy
    numberOfColumns,
    value_cols,
    colName,
    count,
    chartDict,
):
    """
    Converts your Pandas-based logic into a Polars-based approach.
    We do minimal collects for single-row extraction.
    """

    namingParams = get_naming_params()
    positionLegends = namingParams["positionLegends"]
    legendsAtRight = namingParams["legendsAtRight"]
    legendsAtLeft = namingParams["legendsAtLeft"]
    showCAGR = namingParams["showCAGR"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    absolute = namingParams["absolute"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]

    # Early exit if small multiples are being plotted
    # and we don't do the annotation
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        return figure

    # Defaults
    countRows = 1
    countCols = 1
    xShift = get_x_shift_for_data_column(numberOfColumns, chartDict, "row")
    xShift += 70
    yShift = 0
    align = "left"
    xref = "paper"
    indexValue = -2
    indexValueCumSum = -1
    xValue = 1
    ax = xValue
    xAnchor = "auto"
    right_edge_x = _stacked_column_plot_edge_x(figure, "right")
    left_edge_x = _stacked_column_plot_edge_x(figure, "left")
    use_right_column_edge = True

    if positionLegends in chartDict and chartDict[positionLegends] == legendsAtRight:
        if numberOfColumns == 2:
            xShift = 38
            align = "left"
            ax = 1
        elif (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] != absolute
        ):
            indexValue = -1
        elif showCAGR in chartDict and chartDict[showCAGR]:
            indexValue = -2
            xShift = 48
            align = "left"
        else:
            indexValue = -1
            align = "left"
    elif positionLegends in chartDict and chartDict[positionLegends] == legendsAtLeft:
        use_right_column_edge = False
        xShift = -80
        yShift = 0
        align = "right"
        indexValue = 0
        indexValueCumSum = 0
        ax = adjust_ax_by_number_of_columns(numberOfColumns, chartDict)
        xValue = 0
        xref = "paper"
        if left_edge_x is not None:
            xValue = left_edge_x
            ax = left_edge_x
            xref = "x"
            xShift = -10
            xAnchor = "right"

    if use_right_column_edge and right_edge_x is not None:
        xValue = right_edge_x
        ax = right_edge_x
        xref = "x"
        xShift = 10
        xAnchor = "left"

    # We need to extract from Polars.
    # Minimal collects for the single row needed.
    if count == 0:
        val = get_polars_value_at_index(df_lazy, colName, indexValue)
        if val:
            yValue = val * 0.5
        else:
            yValue = 0.5
    else:
        # get half of the value in the current column
        val_this = get_polars_value_at_index(df_lazy, colName, indexValue)
        if val_this:
            val_this = val_this * 0.5
        else:
            val_this = 0
        # add the cumsum from the column below
        colBelowName = value_cols[count - 1]
        val_cum = get_polars_value_at_index(
            dfCumSum_lazy, colBelowName, indexValueCumSum
        )
        val_cum = val_cum or 0
        yValue = val_this + val_cum

    # Possibly break colName if > 14 in length
    if len(colName) > 14:
        firstpart = colName[:8]
        secondpart = colName[8:].replace(" ", " <BR>", 1)
        colName = firstpart + secondpart

    figure.add_annotation(
        text=colName.strip(),
        showarrow=False,
        align=align,
        yshift=yShift,
        y=yValue,
        ax=ax,
        x=xValue,
        xref=xref,
        xshift=xShift,
        xanchor=xAnchor,
        hovertext=colName,
    )

    return figure


def add_totals_below(
    figure: go.Figure,
    chosenChart: str,
    dfCopy: pl.DataFrame | pl.LazyFrame,
    dfCumSum: pl.DataFrame | pl.LazyFrame,
    value_cols: list[str],
    colname: str,
    count: int,
    totalYaxisNumber: int,
    chartDict: dict,
    row: int | None,
    col: int | None,
) -> go.Figure:
    """Add total annotations below bars for Mekko and stacked charts."""

    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    showValuesAs = namingParams["showValuesAs"]
    absolute = namingParams["absolute"]
    valueName = namingParams["valueName"]
    marimekkoChart = namingParams["marimekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    workColumn = namingParams["workColumn"]
    valueName = namingParams["valueName"]
    try:
        from modules.data.multidimensional_charts_prep import sum_ratio_lazy
    except Exception as e:  # pragma: no cover - fallback for stubbed tests
        logging.exception(e)
        _log_debug("draw_charts_utils import error:", e)

        def sum_ratio_lazy(
            df: pl.DataFrame | pl.LazyFrame, num: str, den: str
        ) -> float:
            lf = ensure_lazyframe(df)
            result = lf.select(
                [
                    pl.col(num).sum().alias("__num"),
                    pl.col(den).sum().alias("__den"),
                ]
            ).collect()
            num_v = result["__num"][0]
            den_v = result["__den"][0]
            return 0.0 if not den_v else float(num_v) / float(den_v)

    align = "center"
    yref = "paper"
    y = 0
    lf_copy = ensure_lazyframe(dfCopy)
    lf_cumsum = ensure_lazyframe(dfCumSum)
    if chosenChart in [stackedBarChart]:
        df = lf_copy.slice(1)
        yShift = -13
        if (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] == absolute
        ):
            columnTotalInValue = (
                df.select(pl.col(colname).sum()).collect(engine="streaming").item()
            )
            columnTotalInValue = int(round(columnTotalInValue, 0))
            columnTotalInValue = divide_by_value_prefix(
                columnTotalInValue, chartDict, False
            )
            columnTotalInPercent = int(
                round(sum_ratio_lazy(df, colname, valueName) * 100, 0)
            )
            columnTotalInPercent = " <BR>(" + millify(columnTotalInPercent, 0) + "%)"
            columnTotal = str(columnTotalInValue) + columnTotalInPercent
            current_first = (
                lf_copy.select(pl.col(colname).first())
                .collect(engine="streaming")
                .item()
            )
            if count == 0:
                x = (current_first or 0) * 0.5
            else:
                prev_val = (
                    lf_cumsum.select(pl.col(value_cols[count - 1]).first())
                    .collect(engine="streaming")
                    .item()
                )
                x = (prev_val or 0) + (current_first or 0) * 0.5
            xref = "x"
            ax = x
            xShift = 0
            yShift = yShift
        else:
            dfAbsolute = ensure_polars_df(chartDict[absolute])
            # Use Polars expression to sum the column instead of Series method
            numerator = dfAbsolute.select(pl.col(colname).sum()).item()
            columnTotalInPercent = round(
                sum_ratio_lazy(dfAbsolute, colname, valueName) * 100, 0
            )
            columnTotalInPercent = " <BR>(" + millify(columnTotalInPercent, 0) + "%)"
            columnTotalInValue = int(round(numerator, 0))
            columnTotalInValue = divide_by_value_prefix(
                columnTotalInValue, chartDict, False
            )
            columnTotal = str(columnTotalInValue) + columnTotalInPercent
            current_first = (
                lf_copy.select(pl.col(colname).first())
                .collect(engine="streaming")
                .item()
            )
            if count == 0:
                x = (current_first or 0) * 0.5
            else:
                prev_val = (
                    lf_cumsum.select(pl.col(value_cols[count - 1]).first())
                    .collect(engine="streaming")
                    .item()
                )
                x = (prev_val or 0) + (current_first or 0) * 0.5
            xref = "x"
            ax = x
            xShift = 0
            yShift = yShift
    elif chosenChart in [marimekkoChart]:
        # Column "colname" may sometimes be string-typed (e.g. a dimension). Cast
        # both columns to floats so multiplication never raises a type error.
        df = lf_copy.with_columns(
            (
                pl.col(colname).cast(pl.Float64, strict=False).fill_null(0)
                * pl.col(valueName).cast(pl.Float64, strict=False).fill_null(0)
            ).alias(workColumn)
        )
        columnTotal = 1
        columnTotalInPercent = round(sum_ratio_lazy(df, workColumn, valueName) * 100, 1)
        columnTotalInPercent = "<BR>(" + millify(columnTotalInPercent, 0) + "%)"
        columnTotalInValue = (
            df.select(pl.col(workColumn).sum().round(1))
            .collect(engine="streaming")
            .item()
        )
        value_prefix_name = namingParams["valuePrefixName"]
        mill_dict = {
            "t": 1_000_000_000_000,
            "b": 1_000_000_000,
            "m": 1_000_000,
            "k": 1_000,
            "": 1,
        }
        prefix = chartDict.get(value_prefix_name, "")
        divisor = mill_dict.get(prefix, 1)
        scaled_value = (columnTotalInValue or 0.0) / divisor
        columnTotalInValue = f"{scaled_value:.1f}"
        columnTotal = f"{columnTotalInValue}{columnTotalInPercent}"
        totals_exprs = [
            (
                pl.col(c).cast(pl.Float64, strict=False).fill_null(0)
                * pl.col(valueName).cast(pl.Float64, strict=False).fill_null(0)
            )
            .sum()
            .alias(c)
            for c in value_cols
        ]
        totals_df = lf_copy.select(totals_exprs).collect(engine="streaming")
        totals_row = totals_df.row(0, named=True) if totals_df.height > 0 else {}
        total_sum = 0.0
        for col in value_cols:
            raw_val = totals_row.get(col)
            try:
                total_sum += float(raw_val) if raw_val is not None else 0.0
            except (TypeError, ValueError):
                total_sum += 0.0
        cumulative = 0.0
        x = 0.0
        found = False
        if total_sum > 0:
            for col in value_cols:
                raw_val = totals_row.get(col)
                try:
                    total_val = float(raw_val) if raw_val is not None else 0.0
                except (TypeError, ValueError):
                    total_val = 0.0
                share_val = total_val / total_sum if total_sum else 0.0
                if col == colname:
                    x = cumulative + share_val * 0.5
                    found = True
                    break
                cumulative += share_val
        if not found:
            current_first = (
                lf_copy.select(pl.col(colname).first())
                .collect(engine="streaming")
                .item()
            )
            if count == 0:
                x = (current_first or 0) * 0.5
            else:
                prev_val = (
                    lf_cumsum.select(pl.col(value_cols[count - 1]).first())
                    .collect(engine="streaming")
                    .item()
                )
                x = (prev_val or 0) + (current_first or 0) * 0.5
        xref = "x"
        ax = x
        xShift = 0
        yShift = -40
    annotation_kwargs = {}
    if row is not None and col is not None:
        annotation_kwargs = {"row": row, "col": col}
    figure.add_annotation(
        text=columnTotal,
        showarrow=False,
        align=align,
        yshift=yShift,
        yref=yref,
        y=y,
        ax=ax,
        x=x,
        xref=xref,
        xshift=xShift,
        hovertext=colname,
        **annotation_kwargs,
    )
    return figure


def get_first_value_of_column(df: pl.LazyFrame, col: str, ndigits: int = 1):
    """
    Returns the first row of `col` as a float (rounded to `ndigits`) if it is numeric.
    If the value is not numeric, returns the raw value (as a string).
    If the column/frame is empty, returns None.
    """
    # Materialize only the first row of `col`.
    result = df.select(pl.col(col)).limit(1).collect()
    check_collect("AAAD", "first value", result)
    if result.height == 0:
        return None

    raw_val = result.item(0, 0)
    if raw_val is None:
        return None  # The cell is null

    # Attempt to parse as float; if successful, round and return as float.
    try:
        float_val = float(raw_val)
        return round(float_val, ndigits)
    except (ValueError, TypeError):
        # If it's not numeric, just return the string representation
        return str(raw_val)


def get_last_value_of_column(df: pl.LazyFrame, column: str):
    """
    Return the *last row* of `column` from a lazy frame or None if empty.
    """
    result = df.select(pl.col(column)).tail(1).collect()
    check_collect("ZAAD", "get_last_value_of_column", result)
    if result.height == 0:
        return None
    return result.item(0, 0)


def get_second_to_last_value_of_column(df: pl.LazyFrame, column: str):
    """
    Return the *second-to-last* row of `column` from a lazy frame or None if not enough rows.
    """
    # tail(2) gives the last two rows, head(1) gives the “top” of those two = second-to-last in full DF
    result = df.select(pl.col(column)).tail(2).head(1).collect()
    check_collect("ZAAE", "get_second_to_last_value_of_column", result)
    if result.height == 0:
        return None
    return result.item(0, 0)


def len_of_lazy(df: pl.LazyFrame) -> int:
    """
    Return the number of rows in a lazy frame (requires a minimal collect).
    """
    check_collect("AAAC", "number of rows", df.head())
    return df.select(pl.len()).collect().item(0, 0)


def percentage_cols_lazy(df: pl.LazyFrame, cols: list[str], denom: str) -> pl.LazyFrame:
    """Return ``df`` with ``cols`` multiplied by ``100 / denom`` lazily."""

    exprs = [pl.col(c) * 100 / pl.col(denom) for c in cols]
    return df.with_columns(exprs)


def add_cxgr_on_right(
    figure,
    df: pl.LazyFrame,
    dfCumSum: pl.LazyFrame,
    colName: str,
    numberOfColumns: int,
    value_cols: list,
    count: int,
    chartDict: dict,
):
    """
    Convert your Pandas-based logic to Polars (lazy) equivalents.
    `df` and `dfCumSum` are Polars *lazy* frames.
    We only collect minimal scalars needed for the annotations.
    """

    namingParams = get_naming_params()
    countColumn = namingParams["countColumn"]
    CXGRMetric = namingParams["CXGRMetricName"]
    CXGRData = namingParams["CXGRData"]
    periodsMissing = namingParams["periodsMissing"]
    periodsMissingSymbol = namingParams["periodsMissingSymbol"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    positionLegends = namingParams["positionLegends"]
    legendsAtRight = namingParams["legendsAtRight"]

    # If we're not in small multiples mode...
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:

        # If CXGR is turned on...
        if CXGRMetric in chartDict and chartDict[CXGRMetric]:
            dfCXGR = chartDict[CXGRData]  # Polars LazyFrame containing CXGR
            dfPeriodsMissing = chartDict[
                periodsMissing
            ]  # Polars LazyFrame containing missing periods

            # We'll read chartDict[CXGRMetric] but not sure if it's a boolean or a numeric
            # In your original code, it seemed to store the name or a boolean.
            # We'll keep it as is:
            CXGRMetricVal = chartDict[CXGRMetric]

            xShift = get_x_shift_for_data_column(numberOfColumns, chartDict, "row")
            if (
                positionLegends in chartDict
                and chartDict[positionLegends] == legendsAtRight
            ):
                xShift += 80
            edge_x = _stacked_column_plot_edge_x(figure, "right")
            xValue = 1
            xref = "paper"
            xAnchor = "center"
            if edge_x is not None:
                xValue = edge_x
                xref = "x"
                xShift = -8
                xAnchor = "right"

            # Checking if colName is actually in the schema
            # For lazy frames, columns works if the schema is already known.
            # If not known, you might skip this check or use try/except.
            columns, schema = get_schema_and_column_names(dfCXGR)
            if colName in columns:
                # Grab the first row of colName from dfCXGR
                cxgrValue = get_first_value_of_column(dfCXGR, colName)
                if cxgrValue is not None:
                    cxgrValue = round(cxgrValue, 1)
                    if cxgrValue == 0:
                        cxgrText = ""
                    else:
                        # Convert numeric value to a string with millify and append '%'
                        cxgrText = millify(cxgrValue, 2) + "%"

                        # If we have missing periods info
                        pm_columns, _ = get_schema_and_column_names(dfPeriodsMissing)
                        if len_of_lazy(dfPeriodsMissing) > 0 and colName in pm_columns:
                            pmValue = get_first_value_of_column(
                                dfPeriodsMissing, colName
                            )
                            if pmValue is not None:
                                pmValue = round(pmValue, 1)
                                if pmValue > 0:
                                    cxgrText += periodsMissingSymbol
                    # We compute yValue using second-to-last row from df or dfCumSum
                    if count == 0:
                        # second-to-last from df[colName]
                        valSecondToLast = get_second_to_last_value_of_column(
                            df, colName
                        )
                        if valSecondToLast is None:
                            valSecondToLast = 0
                        yValue = valSecondToLast * 0.5
                    else:
                        colBelowName = value_cols[count - 1]
                        valSecondToLast = get_second_to_last_value_of_column(
                            df, colName
                        )
                        if valSecondToLast is None:
                            valSecondToLast = 0
                        valLastCumSum = get_last_value_of_column(dfCumSum, colBelowName)
                        if valLastCumSum is None:
                            valLastCumSum = 0
                        yValue = valSecondToLast * 0.5 + valLastCumSum

                    # Finally, add the annotation on the figure
                    figure.add_annotation(
                        text=str(cxgrText),
                        showarrow=False,
                        align="right",
                        yshift=0,
                        y=yValue,
                        ax=xValue,
                        x=xValue,
                        xref=xref,
                        xshift=xShift,
                        xanchor=xAnchor,
                        hovertext=colName,
                    )

    return figure


def adjust_tick_text(ticktext, chosenChart, chartDict):
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    addBlankColumn = namingParams["addBlankColumn"]
    if addBlankColumn in chartDict and chartDict[addBlankColumn]:
        if chosenChart in [stackedParetoChart, stackedColumnChart]:
            ticktext.append("     ")
        elif chosenChart in [stackedBarChart]:
            ticktext.append("     ")
    return ticktext


def get_chart_scale(fig, chartDict, paramDict, axis, metric, chartName, key):
    namingParams = get_naming_params()
    configParams = get_config_params()
    uniformTextMinSize = get_uniform_text_min_size(configParams, namingParams)
    columnHash = paramDict[namingParams["columnHash"]]
    fixedScaleValueKey = namingParams["fixedScaleValue"]
    sessionKey = fixedScaleValueKey + "_" + chartName
    fixedScale = False
    currentScale = False
    if key in chartDict and chartDict[key]:
        # hashKey=get_hashed_key(fixedScaleChoiceKey+metric,columnHash)
        try:
            fullFig = fig.full_figure_for_development(warn=False)
        except Exception as exc:  # noqa: BLE001
            logging.exception(exc)
            ui.warning("Unable to calculate fixed chart scale in headless mode.")
            return fig, paramDict
        if axis == "Y":
            fixedScale = fullFig.layout.yaxis.range[1]
        elif axis == "X":
            fixedScale = fullFig.layout.xaxis.range[1]
        if fixedScale:
            if fixedScale > 10:
                currentScale = round(fixedScale, 0)
            else:
                currentScale = round(fixedScale, 2)
        if sessionKey in session_state:
            pass
        else:
            session_state[sessionKey] = currentScale
        if currentScale:
            message = "Chart scale   fixed at " + str(session_state[sessionKey])
            paramDict = add_info_message_in_plot_charts_tab(paramDict, message)
        if sessionKey in session_state:
            currentScale = session_state[sessionKey]
            if axis == "Y":
                fig.update_layout(yaxis_range=[0, currentScale])
            elif axis == "X":
                fig.update_layout(xaxis_range=[0, currentScale])
        else:
            pass
    return fig, paramDict


def keep_same_scale_for_all_plots(fig, metric, metricType, fullFig, axis):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    discountPerUnit = namingParams["discountPerUnitName"]
    discountPerVolumeName = namingParams["discountPerVolumeName"]
    valueMetric = namingParams["valueMetric"]
    priceMetric = namingParams["priceMetric"]
    percentMetric = namingParams["percentMetric"]
    discountMetric = namingParams["discountMetric"]
    metricDict = {
        valueMetric: valueMetricsArray,
        priceMetric: priceMetricsArray,
        percentMetric: percentMetricsArray,
        discountMetric: [discountPerUnit, discountPerVolumeName],
    }
    if not fullFig:
        try:
            fullFig = fig.full_figure_for_development(warn=False)
        except Exception as exc:  # noqa: BLE001
            logging.exception(exc)
            ui.warning("Unable to calculate shared chart scale in headless mode.")
            fullFig = fig
        for metricClass in metricDict:
            if metric in metricDict[metricClass]:
                metricType = metricClass
    elif metricType and metric in metricDict[metricType]:
        if axis == "Y":
            range_values = fullFig.layout.yaxis.range
            if range_values and len(range_values) > 1:
                fig.update_layout(yaxis_range=[0, range_values[1]])
        elif axis == "X":
            range_values = fullFig.layout.xaxis.range
            if range_values and len(range_values) > 1:
                fig.update_layout(xaxis_range=[0, range_values[1]])
            try:
                pass
                # fig.update_layout(xaxis2={"range":[-fullFig.layout.xaxis.range[1],fullFig.layout.xaxis.range[1]]})
            except Exception as e:  # noqa: BLE001  # nosec B110
                logging.exception(e)
                ui.error("Something went wrong while importing draw_charts_utils.")
    else:
        pass
    return fig, fullFig, metricType


def add_cumulated_legends(
    figure, df, dfCumSum, numberOfColumns, value_cols, uniqueItems, count, chartDict
):
    from modules.utilities.utils import get_row_count

    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    positionLegends = namingParams["positionLegends"]
    legendsAtRight = namingParams["legendsAtRight"]
    legendsAtLeft = namingParams["legendsAtLeft"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    colName = uniqueItems[count]
    countRows = 1
    countCols = 1
    xShift = 85
    yShift = 0
    align = "left"
    xref = "x"
    indexValue = -1
    row_count = get_row_count(df)
    xValue = row_count - 1
    ax = xValue
    if positionLegends in chartDict and chartDict[positionLegends] == legendsAtLeft:
        xShift = -xShift
        yShift = 0
        align = "right"
        indexValue = 0
        ax = adjust_ax_by_number_of_columns(numberOfColumns, chartDict)
        xValue = 0
        xref = "x"
    # Use Polars-safe scalar extraction rather than pandas-style indexing
    df_lazy = ensure_lazyframe(df)
    columns, schema = get_schema_and_column_names(df_lazy)
    axis_col = dateName if dateName in columns else None
    if axis_col is None:
        date_like_cols = [
            name
            for name, dtype in schema.items()
            if dtype in {pl.Date, pl.Datetime, pl.Datetime("ns"), pl.Datetime("us")}
        ]
        axis_col = date_like_cols[0] if date_like_cols else None
    if axis_col is not None:
        xValue = get_polars_value_at_index(df_lazy, axis_col, indexValue)
        ax = xValue
    val_this = get_polars_value_at_index(df_lazy, colName, indexValue)
    previous_cols = [item for item in uniqueItems[:count] if item in columns]
    val_below = 0.0
    for previous_col in previous_cols:
        previous_value = get_polars_value_at_index(df_lazy, previous_col, indexValue)
        val_below += float(previous_value or 0)
    yValue = (val_this or 0) * 0.5 + val_below
    if len(colName) > 14:
        colName = colName.replace(" ", " <BR>", 1)
    figure.add_annotation(
        text=colName,
        showarrow=False,
        align=align,
        yshift=yShift,
        y=yValue,
        ax=ax,
        x=xValue,
        xref=xref,
        xshift=xShift,
        hovertext=colName,
        row=countRows,
        col=countCols,
    )
    return figure


def add_positive_outlier_pins_to_column(fig, df, largestArray, colorDict, colNumber):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    differenceInPercent = namingParams["differenceInPercent"]
    if len(largestArray) > 1:
        color = colorDict["greenColor"]
        if largestArray[2] == 1:
            color = colorDict["redColor"]
        rounded_value = int(round(float(largestArray[1]), 0))
        label = str(rounded_value)
        if rounded_value > 0:
            label = "+" + label + "%"
        label = "<i>" + label + "</i>"
        # Polars-safe max extraction
        lf = ensure_lazyframe(df)
        diff_col = pl.col(differenceInPercent)
        max_df = lf.select(diff_col.max().alias("__max")).collect(engine="streaming")
        col_max = max_df["__max"][0] if max_df.height else 0
        col_max = float(col_max or 0)
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=4,
            line_color=color,
            x1=largestArray[0],
            x0=largestArray[0],
            yref="paper",
            y1=0,
            y0=col_max * 1.2,
            xref="x",
            row=1,
            col=colNumber,
        )
        fig.add_annotation(
            showarrow=True,
            arrowcolor=color,
            arrowhead=2,
            arrowsize=3,
            arrowwidth=1,
            xanchor="center",
            x=largestArray[0],  # arrows' head
            ax=largestArray[0],  # arrows' tail
            yref="paper",
            ayref="y",
            y=col_max * 1.6,  # arrows' head
            ay=col_max * 1,  # arrows' tail
            xref="x",
            axref="x",
            align="center",
            row=1,
            col=colNumber,
        )
        fig.add_annotation(
            text=label,
            showarrow=False,
            # xanchor="center",
            xshift=-5,
            x=largestArray[0],  # arrows' head
            ax=0,  # arrows' tail
            yref="paper",
            ayref="y",
            y=col_max * 1.2,  # arrows' head
            xref="x",
            axref="x",
            align="center",
            row=1,
            col=colNumber,
        )
    return fig


def add_negative_outlier_pins_to_column(fig, df, smallestArray, colorDict, colNumber):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    differenceInPercent = namingParams["differenceInPercent"]
    if len(smallestArray) > 1:
        color = colorDict["greenColor"]
        if smallestArray[2] == 1:
            color = colorDict["redColor"]
        label = str(int(round(float(smallestArray[1]), 0)))
        label = "<i>" + label + "%" + "</i>"
        # Polars-safe max extraction
        lf = ensure_lazyframe(df)
        diff_col = pl.col(differenceInPercent)
        max_df = lf.select(diff_col.max().alias("__max")).collect(engine="streaming")
        col_max = max_df["__max"][0] if max_df.height else 0
        col_max = float(col_max or 0)
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=4,
            line_color=color,
            x1=smallestArray[0],
            x0=smallestArray[0],
            yref="paper",
            y1=0,
            y0=-col_max * 1.2,
            xref="x",
            row=1,
            col=colNumber,
        )
        fig.add_annotation(
            showarrow=True,
            arrowcolor=color,
            arrowhead=2,
            arrowsize=3,
            arrowwidth=1,
            xanchor="center",
            x=smallestArray[0],  # arrows' head
            ax=smallestArray[0],  # arrows' tail
            yref="paper",
            ayref="y",
            y=-col_max * 1.6,  # arrows' head
            ay=-col_max * 1,  # arrows' tail
            xref="x",
            axref="x",
            align="center",
            row=1,
            col=colNumber,
        )
        fig.add_annotation(
            text=label,
            showarrow=False,
            # xanchor="center",
            xshift=-5,
            x=smallestArray[0],  # arrows' head
            ax=smallestArray[0],  # arrows' tail
            yref="paper",
            ayref="y",
            y=-col_max * 1,  # arrows' head
            xref="x",
            axref="x",
            align="center",
            row=1,
            col=colNumber,
        )
    return fig


def add_pinheads_to_multitier_column(fig, df, textposition, orientation):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    dateName = namingParams["dateName"]
    labelName = namingParams["labelName"]
    differenceInPercent = namingParams["differenceInPercent"]
    # Ensure Polars lists for Plotly (avoid pandas-like Series passing)
    lf = ensure_lazyframe(df)
    lists = to_lists(lf, [dateName, differenceInPercent, labelName])
    fig.add_trace(
        go.Scatter(
            x=lists[dateName],
            y=lists[differenceInPercent],
            text=lists[labelName],
            mode="markers+text",
            marker_symbol="square",
            marker_color="black",
            marker_standoff=4,
            marker_angle=-90,
            marker_size=7,
            textposition=textposition,
            cliponaxis=False,
            orientation=orientation,
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    return fig


def add_percent_change_markers_to_column(fig, dfCopy, colorChoice, lineWidth, constant):
    from modules.utilities.utils import get_row_count

    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    colorName = namingParams["colorName"]
    labelName = namingParams["labelName"]
    workColumn = namingParams["workColumn"]
    differenceInPercent = namingParams["differenceInPercent"]
    orientation = "v"
    textposition = make_text_position_array(dfCopy, orientation)
    lf = utils.ensure_lazyframe(dfCopy)
    row_count = get_row_count(lf)
    df = lf.collect(engine="streaming")
    anchosPercent = [0.48 / 10] * row_count
    offset = 0.1
    fig = add_pinheads_to_multitier_column(fig, df, textposition, orientation)
    fig.add_trace(
        go.Bar(
            x=to_lists(lf, [dateName])[dateName],
            y=to_lists(lf, [differenceInPercent])[differenceInPercent],
            marker=dict(
                color=list(map(colorChoice, to_lists(lf, [colorName])[colorName]))
            ),
            width=anchosPercent,
            name=differenceInPercent,
            orientation=orientation,
            offset=offset,
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    return fig


def check_small_multiples_total(
    dfSmallMultiples, dfNotSmallMultiples, metricToPlot, chartDict
):
    namingParams = get_naming_params()
    chosenChart = namingParams["chosenChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    scatterChart = namingParams["scatterChart"]
    bubbleChart = namingParams["bubbleChart"]
    bubbleSize = namingParams["bubbleSize"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    periodName = namingParams["periodName"]
    valueName = namingParams["valueName"]
    multipliedMetric = namingParams["multipliedMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    chosenChart = chartDict[chosenChart]
    canCheck = True
    dfSmallMultiples = ensure_polars_df(dfSmallMultiples)
    dfNotSmallMultiples = ensure_polars_df(dfNotSmallMultiples)

    if chosenChart in [marimekkoChart]:
        totalNotSmallMultiples = extract_scalar(
            dfNotSmallMultiples.select(pl.col(metricToPlot).sum())
        )
        dfSmallMultiples = coerce_numeric_columns(dfSmallMultiples)
        dfSmallMultiples = dfSmallMultiples.select(pl.selectors.numeric())
        totalSmallMultiples = (
            dfSmallMultiples.select(
                pl.all().sum()
            )  # 1) sum each column  # → shape: (1, n)
            .select(
                pl.sum_horizontal(pl.all()).sum()
            )  # 2) sum horizontally across those n columns  # → shape: (1, 1)
            .item()  # 3) scalar  ➜  ✔
        )

    elif chosenChart in [barmekkoChart]:
        totalNotSmallMultiples = extract_scalar(
            dfNotSmallMultiples.select(pl.col(chartDict[multipliedMetric]).sum())
        )
        # Prefer Polars expression over Series arithmetic for clarity
        totalSmallMultiples = extract_scalar(
            dfSmallMultiples.select(
                (pl.col(chartDict[yAxisMetric]) * pl.col(chartDict[xAxisMetric])).sum()
            )
        )
    elif chosenChart in [bubbleChart]:
        totalNotSmallMultiples = extract_scalar(
            dfNotSmallMultiples.select(pl.col(chartDict[bubbleSize]).sum())
        )
        totalSmallMultiples = extract_scalar(
            dfSmallMultiples.select(pl.col(chartDict[bubbleSize]).sum())
        )
    elif chosenChart in [stackedBarChart]:
        toPlotPeriod = chartDict[toPlotPeriod]
        # pandas-style boolean masking → Polars filter
        dfNotSmallMultiples = dfNotSmallMultiples.filter(
            pl.col(periodName) == toPlotPeriod
        )
        columns, schema = get_schema_and_column_names(dfSmallMultiples)
        if metricToPlot in columns:
            totalSmallMultiples = extract_scalar(
                dfSmallMultiples.select(pl.col(metricToPlot).sum())
            )
        else:
            totalSmallMultiples = extract_scalar(
                dfSmallMultiples.select(pl.col(valueName).sum())
            )
        columns, schema = get_schema_and_column_names(dfNotSmallMultiples)
        if metricToPlot in columns:
            totalNotSmallMultiples = extract_scalar(
                dfNotSmallMultiples.select(pl.col(metricToPlot).sum())
            )
        else:
            canCheck = False
            totalNotSmallMultiples = 0.0
    elif chosenChart in [scatterChart]:
        columns, _ = get_schema_and_column_names(dfSmallMultiples)
        if metricToPlot and metricToPlot in columns:
            totalSmallMultiples = extract_scalar(
                dfSmallMultiples.select(pl.col(metricToPlot).sum())
            )
            totalNotSmallMultiples = extract_scalar(
                dfNotSmallMultiples.select(pl.col(metricToPlot).sum())
            )
        else:
            dfSmallMultiples = coerce_numeric_columns(dfSmallMultiples)
            dfSmallMultiples = dfSmallMultiples.select(pl.selectors.numeric())
            dfNotSmallMultiples = coerce_numeric_columns(dfNotSmallMultiples)
            dfNotSmallMultiples = dfNotSmallMultiples.select(pl.selectors.numeric())
            totalSmallMultiples = extract_scalar(
                dfSmallMultiples.select(pl.all().sum())
            )
            totalNotSmallMultiples = extract_scalar(
                dfNotSmallMultiples.select(pl.all().sum())
            )
    if canCheck:
        check_percentage_difference(totalSmallMultiples, totalNotSmallMultiples)
    else:
        ui.info("Could not check if totals match.")
    return None


def add_separator_on_axis(fig, df, y, yref, row, col):
    from modules.utilities.utils import get_row_count

    lineWidth = 10
    color = "#FFFFFF"
    # Use Polars row-count helper rather than direct .height check
    if get_row_count(df) == 14:
        idx_val = get_row_count(df) - 2
        fig.add_shape(
            type="rect",
            fillcolor=color,
            opacity=1,
            layer="above",
            line_width=lineWidth,
            line_color=color,
            y0=+0,
            y1=y,
            yref=yref,
            x0=idx_val - 0.3,
            x1=idx_val + 0.5,
            xref="x",
            row=row,
            col=col,
        )
    return fig


def check_percentage_difference(
    value1: int | float | pl.Series | pl.DataFrame,
    value2: int | float | pl.Series | pl.DataFrame,
) -> None:
    """Report if totals differ by more than 1%.

    Parameters
    ----------
    value1, value2:
        Numeric inputs that can be ``int``/``float`` scalars, ``polars.Series``
        or single-column ``polars.DataFrame`` objects.
    """

    v1 = float(extract_scalar(value1))
    v2 = float(extract_scalar(value2))

    if v1 == 0 and v2 == 0:
        return None
    elif v1 == 0 or v2 == 0:
        ui.error("One of the values is zero, cannot calculate percentage difference.")
        return None

    percentage_difference = abs((v1 - v2) / v1) * 100
    if percentage_difference > 1:
        percentage_difference = round(percentage_difference, 1)
        ui.error(
            "Small multiples values and total values differ by "
            + str(percentage_difference)
            + "%"
        )
        ui.error("Small multiples total is  " + str(v1))
        ui.error("Total is  " + str(v2))
    else:
        ui.success("Total and small multiples values match")
    return None


def add_line_traces(
    fig,
    df,
    element,
    uniqueItems,
    colorArray,
    labelArray,
    yShiftArray,
    xShiftArray,
    chartDict,
    countRows,
    countCols,
    count,
):
    from modules.utilities.utils import get_row_count

    namingParams = get_naming_params()
    yShiftName = namingParams["yShiftName"]
    xShiftName = namingParams["xShiftName"]
    labelName = namingParams["labelName"]
    separatorString = namingParams["separatorString"]
    labelArray.append(element + separatorString + labelName)
    yShiftArray.append(element + separatorString + yShiftName)
    xShiftArray.append(element + separatorString + xShiftName)
    positions = list(range(get_row_count(df)))
    # Round series via Polars expressions (avoid pandas-style round on Series)
    lf = ensure_lazyframe(df)
    col_name = uniqueItems[count]
    y_series_df = lf.select(
        pl.col(col_name).cast(pl.Float64, strict=False).round(1).alias(col_name)
    ).collect(engine="streaming")
    y_vals = y_series_df[col_name].to_list()
    fig.add_trace(
        go.Scatter(
            x=positions,
            y=y_vals,
            line=dict(color=colorArray[count]),
            showlegend=False,
            mode="lines+markers",
            hovertext=element,
        ),
        row=countRows,
        col=countCols,
    )
    count = count + 1
    return fig, labelArray, yShiftArray, xShiftArray, count


def add_non_cumulated_legends(
    fig,
    data: Mapping[str, list] | pl.DataFrame | pl.LazyFrame,
    chosenChart,
    uniqueItems,
    chartDict,
    countRows,
    countCols,
    count,
):

    namingParams = get_naming_params()
    positionLegends = namingParams["positionLegends"]
    legendsAtRight = namingParams["legendsAtRight"]
    legendsAtLeft = namingParams["legendsAtLeft"]
    slopeChart = namingParams["slopeChart"]
    positionIndex = -1
    xShift = 85
    align = "left"
    if positionLegends in chartDict and chartDict[positionLegends] == legendsAtLeft:
        positionIndex = 0
        xShift = -85
        align = "right"

    if isinstance(data, (pl.DataFrame, pl.LazyFrame)):
        lf = ensure_lazyframe(data)
        y_values = to_lists(lf, [uniqueItems[count]])[uniqueItems[count]]
    else:
        y_values = data[uniqueItems[count]]

    idx_vals = list(range(len(y_values)))
    x = idx_vals[positionIndex]
    fig.add_annotation(
        text=uniqueItems[count],
        showarrow=False,
        x=x,
        xshift=xShift,
        xref="x",
        align=align,
        yshift=0,
        y=y_values[positionIndex],
        yref="y",
        hovertext=uniqueItems[count],
        row=countRows,
        col=countCols,
    )
    return fig


def get_labels_for_trend_comparison(df, yArray, metric, chartDict):
    from modules.utilities.utils import get_row_count

    """
    identify the extreme values we want to show
    """
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    labelName = namingParams["labelName"]
    otherLabelName = namingParams["otherLabelName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    discountInPercentName = namingParams["discountInPercentName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    oneBlackValue = namingParams["oneBlackValue"]
    metConditionValue = namingParams["metConditionValue"]
    maxValueKey = namingParams["maxValue"]
    is_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    lf = lf.with_columns(
        pl.col(yArray[0]).alias(workColumn),
        pl.col(yArray[1]).alias(workColumnTwo),
    )

    decimals = 1
    if metric in [discountInPercentName]:
        lf = lf.with_columns(
            (pl.col(workColumn) * 100).alias(workColumn),
            (pl.col(workColumnTwo) * 100).alias(workColumnTwo),
        )
        decimals = 0

    lf = lf.with_columns(
        pl.lit(oneBlackValue).alias(labelName),
        pl.lit(oneBlackValue).alias(otherLabelName),
        pl.col(workColumn).fill_null(0).alias(workColumn),
        pl.col(workColumnTwo).fill_null(0).alias(workColumnTwo),
    )

    stats = lf.select(
        pl.col(workColumn).arg_max().alias("__ac_max_idx"),
        pl.col(workColumn).arg_min().alias("__ac_min_idx"),
        pl.col(workColumnTwo).arg_max().alias("__py_max_idx"),
        pl.col(workColumnTwo).arg_min().alias("__py_min_idx"),
        pl.len().alias("__row_count"),
        pl.col(maxValueKey).max().alias("__max_value"),
        pl.col(workColumn).first().alias("__first_val"),
        pl.col(workColumn).max().alias("__ac_max_val"),
        pl.col(workColumn).min().alias("__ac_min_val"),
        pl.col(workColumnTwo).max().alias("__py_max_val"),
        pl.col(workColumnTwo).min().alias("__py_min_val"),
    ).collect(engine="streaming")

    ac_max_idx = int(stats[0, "__ac_max_idx"])
    ac_min_idx = int(stats[0, "__ac_min_idx"])
    py_max_idx = int(stats[0, "__py_max_idx"])
    py_min_idx = int(stats[0, "__py_min_idx"])
    row_count = int(stats[0, "__row_count"])
    last_idx = row_count - 1
    maxValue = stats[0, "__max_value"]

    prefix, chartDict, decimals = get_number_prefix(maxValue, chartDict, None, False)

    first_prefix = divide_by_value_prefix(stats[0, "__first_val"], chartDict, False)
    ac_max_prefix = divide_by_value_prefix(stats[0, "__ac_max_val"], chartDict, False)
    ac_min_prefix = divide_by_value_prefix(stats[0, "__ac_min_val"], chartDict, False)
    py_max_prefix = divide_by_value_prefix(stats[0, "__py_max_val"], chartDict, False)
    py_min_prefix = divide_by_value_prefix(stats[0, "__py_min_val"], chartDict, False)

    lf = lf.with_row_index("__idx")

    label_expr = pl.col(labelName)
    label_expr = (
        pl.when(pl.col("__idx") == 0).then(pl.lit(first_prefix)).otherwise(label_expr)
    )
    label_expr = (
        pl.when(pl.col("__idx") == last_idx)
        .then(pl.lit(first_prefix))
        .otherwise(label_expr)
    )
    if ac_max_idx != metConditionValue:
        label_expr = (
            pl.when(pl.col("__idx") == ac_max_idx)
            .then(pl.lit(ac_max_prefix))
            .otherwise(label_expr)
        )
    if ac_min_idx != metConditionValue:
        label_expr = (
            pl.when(pl.col("__idx") == ac_min_idx)
            .then(pl.lit(ac_min_prefix))
            .otherwise(label_expr)
        )

    other_expr = pl.col(otherLabelName)
    if py_max_idx not in {ac_max_idx, ac_min_idx, 0, last_idx}:
        other_expr = (
            pl.when(pl.col("__idx") == py_max_idx)
            .then(pl.lit(py_max_prefix))
            .otherwise(other_expr)
        )
    if py_min_idx not in {ac_max_idx, ac_min_idx, 0, last_idx}:
        other_expr = (
            pl.when(pl.col("__idx") == py_min_idx)
            .then(pl.lit(py_min_prefix))
            .otherwise(other_expr)
        )

    lf = lf.with_columns(
        [label_expr.alias(labelName), other_expr.alias(otherLabelName)]
    )

    if metric in percentMetricsArray:
        lf = lf.with_columns(
            [
                pl.when(pl.col(labelName) != oneBlackValue)
                .then(pl.concat_str([pl.col(labelName).cast(str), pl.lit("%")]))
                .otherwise(pl.col(labelName))
                .alias(labelName),
                pl.when(pl.col(otherLabelName) != oneBlackValue)
                .then(pl.concat_str([pl.col(otherLabelName).cast(str), pl.lit("%")]))
                .otherwise(pl.col(otherLabelName))
                .alias(otherLabelName),
            ]
        )

    lf = drop_columns(lf, [workColumn, workColumnTwo, "__idx"])

    if is_lazy:
        return lf, chartDict
    return lf.collect(engine="streaming"), chartDict
