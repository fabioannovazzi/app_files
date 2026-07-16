"""Headless adapters for vendored legacy mix/contribution charts."""

from __future__ import annotations

import calendar
import contextlib
import html
import os
import re
import shutil
import subprocess
import sys
import traceback
import warnings
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Sequence

import polars as pl
from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "LegacyPreparedDataCache",
    "LegacyMixChartExport",
    "cleanup_legacy_imports",
    "write_legacy_mix_chart",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PLUGIN_ROOT / "vendor"
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_VENDOR_ROOT = REPO_ROOT / "plugins" / "_shared" / "vendor"
STACKED_BAR_SMALL_MULTIPLE_AXIS_SPACER = "__mix_axis_spacer__"
STACKED_BAR_SMALL_MULTIPLE_MIN_ROW_SLOTS = 12
SYNTHESIS_TOTAL_PERCENT_LABEL = "100%"
BARMEEKKO_SMALL_MULTIPLE_MIN_WIDTH = 1500
BARMEEKKO_SMALL_MULTIPLE_MIN_HEIGHT = 650
BARMEEKKO_SMALL_MULTIPLE_RIGHT_MARGIN = 130
BARMEEKKO_SMALL_MULTIPLE_LABEL_RANGE_PADDING = 1.15


def _prepare_legacy_import_parent(parent: Path) -> None:
    parent_text = str(parent)
    while parent_text in sys.path:
        sys.path.remove(parent_text)
    sys.path.insert(0, parent_text)
    repo_root_text = str(REPO_ROOT)
    if repo_root_text not in sys.path:
        sys.path.append(repo_root_text)
    module_root = (parent / "modules").resolve()
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            if not module_file or not Path(module_file).resolve().is_relative_to(
                module_root
            ):
                del sys.modules[name]


_prepare_legacy_import_parent(
    SHARED_VENDOR_ROOT
    if (SHARED_VENDOR_ROOT / "modules" / "__init__.py").exists()
    else VENDOR_ROOT
)
from modules.charting.static_export import (  # noqa: E402
    normalize_plotly_figure_for_static_export,
)
from modules.charting.chart_primitives import (  # noqa: E402
    FOCUS_ITEM_HIGHLIGHT_COLOR,
    FOCUS_ITEM_HIGHLIGHT_MAX_ITEMS,
)
from modules.chart_harness import (  # noqa: E402
    is_scenario_label,
    plain_plotly_title_text,
    plotly_title_lines,
    reporting_period_line_from_recipe,
    reporting_title_html,
)

CANONICAL_DATE = "Date"
CANONICAL_PERIOD = "Period"
LEGACY_TOTAL_COLUMN_DIMENSION = "Total View"
# IBCS-style scenario abbreviations: AC=Actual, PY=Previous year,
# PM=Previous month, PQ=Previous quarter, PL=Plan.
CURRENT_PERIOD = "AC"
RELATED_METRIC_MARKER_COLOR = FOCUS_ITEM_HIGHLIGHT_COLOR
RELATED_METRIC_MARKER_SIZE = 18
STACKED_PARETO_METRIC_LABEL_COLUMN = "__stacked_pareto_metric"
LEGACY_NARROW_VERTICAL_BAR_MAX_WIDTH = 360
LEGACY_NARROW_VERTICAL_BAR_RIGHT_PADDING = 180
HEADLESS_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


@dataclass(frozen=True)
class LegacyMixChartExport:
    """Exported paths and audit information for one legacy chart attempt."""

    paths: list[str]
    audit: dict[str, Any]
    chart_context: dict[str, Any] | None = None


@dataclass
class LegacyPreparedDataCache:
    """Prepared grouped data reused by legacy chart render calls."""

    mekko_base_frames: dict[tuple[Any, ...], pl.DataFrame]
    mekko_grouped_frames: dict[tuple[Any, ...], pl.DataFrame]
    stage_frames: dict[tuple[Any, ...], pl.DataFrame]
    stage_payloads: dict[tuple[Any, ...], Any]
    hits: int = 0
    misses: int = 0
    base_hits: int = 0
    base_misses: int = 0
    stage_hits: int = 0
    stage_misses: int = 0

    @classmethod
    def empty(cls) -> "LegacyPreparedDataCache":
        """Return an empty cache for one plugin run."""

        return cls(
            mekko_base_frames={},
            mekko_grouped_frames={},
            stage_frames={},
            stage_payloads={},
        )

    def snapshot(self) -> tuple[int, int, int, int, int, int]:
        """Return current cache hit/miss counters."""

        return (
            self.hits,
            self.misses,
            self.base_hits,
            self.base_misses,
            self.stage_hits,
            self.stage_misses,
        )

    def audit_delta(self, start: tuple[int, int, int, int, int, int]) -> dict[str, Any]:
        """Return cache activity since ``start``."""

        (
            start_hits,
            start_misses,
            start_base_hits,
            start_base_misses,
            start_stage_hits,
            start_stage_misses,
        ) = start
        return {
            "prepared_data_cache": {
                "enabled": True,
                "scope": "legacy_chart_prepared_data",
                "hits": self.hits - start_hits,
                "misses": self.misses - start_misses,
                "base_hits": self.base_hits - start_base_hits,
                "base_misses": self.base_misses - start_base_misses,
                "stage_hits": self.stage_hits - start_stage_hits,
                "stage_misses": self.stage_misses - start_stage_misses,
                "stored_base_frames": len(self.mekko_base_frames),
                "stored_grouped_frames": len(self.mekko_grouped_frames),
                "stored_stage_frames": len(self.stage_frames),
                "stored_stage_payloads": len(self.stage_payloads),
            }
        }

    @staticmethod
    def _columns(frame: pl.DataFrame | pl.LazyFrame) -> list[str]:
        if isinstance(frame, pl.DataFrame):
            return frame.columns
        return frame.collect_schema().names()

    @staticmethod
    def _unique_existing(items: list[Any], source_columns: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if not isinstance(item, str) or item not in source_columns or item in seen:
                continue
            result.append(item)
            seen.add(item)
        return result

    @staticmethod
    def _frame_signature(frame: pl.DataFrame | pl.LazyFrame) -> tuple[Any, ...]:
        columns = LegacyPreparedDataCache._columns(frame)
        if isinstance(frame, pl.DataFrame):
            return ("df", tuple(columns), frame.height)
        try:
            return ("lf", tuple(columns), frame.explain(optimized=True))
        except (pl.exceptions.PolarsError, TypeError, ValueError):
            return ("lf", tuple(columns), id(frame))

    @staticmethod
    def _collect_frame(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
        if isinstance(frame, pl.DataFrame):
            return frame
        try:
            return frame.collect(engine="streaming")
        except pl.exceptions.PolarsError:
            return frame.collect()

    def get_lazy_stage_frame(
        self,
        stage: str,
        key_parts: tuple[Any, ...],
        builder: Callable[[], pl.DataFrame | pl.LazyFrame],
    ) -> pl.LazyFrame:
        """Return a cached prepared stage frame as a LazyFrame."""

        key = (stage, *key_parts)
        cached = self.stage_frames.get(key)
        if cached is not None:
            self.stage_hits += 1
            return cached.lazy()
        collected = self._collect_frame(builder())
        self.stage_frames[key] = collected
        self.stage_misses += 1
        return collected.lazy()

    def get_staged_payload(
        self,
        stage: str,
        key_parts: tuple[Any, ...],
        builder: Callable[[], Any],
    ) -> Any:
        """Return cached non-frame preparation output."""

        key = (stage, *key_parts)
        if key in self.stage_payloads:
            self.stage_hits += 1
            return self.stage_payloads[key]
        payload = builder()
        self.stage_payloads[key] = payload
        self.stage_misses += 1
        return payload

    def get_show_only_largest(
        self,
        names: dict[str, str],
        original: Callable[..., Any],
        df_copy: pl.DataFrame | pl.LazyFrame,
        column: str,
        second_column: str | None,
        time_column: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
        param_dict: dict[str, Any],
        key: str,
    ) -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
        """Cache legacy top-N/other-bucket preparation."""

        axis_config = chart_dict.get(key, {})
        cache_key = (
            self._frame_signature(df_copy),
            chart_dict.get(names["chosenChart"]),
            column,
            second_column,
            time_column,
            tuple(value_cols),
            key,
            axis_config.get(names["numberOfTop"]),
            axis_config.get(names["aggregateOtherItems"]),
        )

        def build() -> tuple[pl.DataFrame, list[Any], Any, list[str]]:
            frame, unique_items, aggregate_other, prepared_value_cols = original(
                df_copy,
                column,
                second_column,
                time_column,
                value_cols,
                chart_dict,
                param_dict,
                key,
            )
            return (
                self._collect_frame(frame),
                list(unique_items),
                aggregate_other,
                list(prepared_value_cols),
            )

        frame, unique_items, aggregate_other, prepared_value_cols = (
            self.get_staged_payload(
                "show_only_largest",
                cache_key,
                build,
            )
        )
        return (
            frame.lazy(),
            list(unique_items),
            aggregate_other,
            list(prepared_value_cols),
        )

    def get_pareto_prepared(
        self,
        names: dict[str, str],
        original: Callable[..., Any],
        df_copy: pl.DataFrame | pl.LazyFrame,
        period: str,
        metric: str,
        chart_dict: dict[str, Any],
        param_dict: dict[str, Any],
        color_list_dict: dict[str, Any],
        class_color_dict: dict[str, Any],
        count: int,
    ) -> tuple[pl.LazyFrame, list[Any], dict[str, Any], str, str]:
        """Cache legacy Pareto preparation for each dimension/metric grain."""

        count_column = chart_dict.get(names["countColumn"])
        aggregate_dimension = chart_dict.get(names["aggregateUniquesDimension"])
        cache_key = (
            self._frame_signature(df_copy),
            period,
            metric,
            count,
            count_column,
            aggregate_dimension,
            bool(chart_dict.get(names["aggregateUniquesByDimension"])),
        )

        def build() -> tuple[pl.DataFrame, list[Any], dict[str, Any], str, str]:
            frame, colors, prepared_class_color_dict, prepared_metric, ratio = original(
                df_copy,
                period,
                metric,
                chart_dict,
                param_dict,
                color_list_dict,
                class_color_dict,
                count,
            )
            return (
                self._collect_frame(frame),
                list(colors),
                dict(prepared_class_color_dict),
                str(prepared_metric),
                str(ratio),
            )

        frame, colors, prepared_class_color_dict, prepared_metric, ratio = (
            self.get_staged_payload("pareto_prepared", cache_key, build)
        )
        class_color_dict.update(prepared_class_color_dict)
        return frame.lazy(), list(colors), class_color_dict, prepared_metric, ratio

    def _target_mekko_columns(
        self,
        names: dict[str, str],
        column: str,
        small_multiples_column_array: list[str],
        value_cols: list[str],
        chart_dict: dict[str, Any],
        source_columns: list[str],
    ) -> tuple[list[str], list[str]]:
        nothing = names["nothingFilteredName"]
        not_met = names["notMetConditionValue"]
        small_multiples_dimension = chart_dict[names["smallMultiplesColumn"]]
        vertical_dimension = chart_dict[names["xAxisDimension"]]
        horizontal_dimension = chart_dict[names["yAxisDimension"]]
        total_name = names["totalName"]
        period_name = names["periodName"]
        group_cols = list(small_multiples_column_array) + [period_name]
        if (
            horizontal_dimension not in [nothing, False, not_met]
            and horizontal_dimension not in group_cols
        ):
            group_cols = list(small_multiples_column_array) + [
                period_name,
                horizontal_dimension,
            ]
        if (
            column != small_multiples_dimension
            and small_multiples_dimension != horizontal_dimension
            and small_multiples_dimension in group_cols
        ):
            group_cols.remove(small_multiples_dimension)
        if column == small_multiples_dimension and total_name in group_cols:
            group_cols.remove(total_name)
        if vertical_dimension and vertical_dimension not in group_cols:
            group_cols.append(vertical_dimension)
        if horizontal_dimension != nothing and horizontal_dimension not in group_cols:
            group_cols.append(horizontal_dimension)
        return (
            self._unique_existing(group_cols, source_columns),
            self._unique_existing(value_cols, source_columns),
        )

    def _base_mekko_columns(
        self,
        names: dict[str, str],
        target_group_cols: list[str],
        small_multiples_column_array: list[str],
        chart_dict: dict[str, Any],
        source_columns: list[str],
        family_dimensions: list[str] | None,
    ) -> list[str]:
        candidates = [
            names["periodName"],
            names["totalName"],
            *(family_dimensions or []),
            chart_dict.get(names["xAxisDimension"]),
            chart_dict.get(names["yAxisDimension"]),
            chart_dict.get(names["smallMultiplesColumn"]),
            *small_multiples_column_array,
            *target_group_cols,
        ]
        return self._unique_existing(candidates, source_columns)

    def _get_mekko_base_frame(
        self,
        df_copy: pl.DataFrame | pl.LazyFrame,
        base_group_cols: list[str],
        value_cols: list[str],
    ) -> pl.DataFrame:
        base_key = ("base", tuple(base_group_cols), tuple(value_cols))
        cached = self.mekko_base_frames.get(base_key)
        if cached is not None:
            self.base_hits += 1
            return cached

        lf = df_copy.lazy() if isinstance(df_copy, pl.DataFrame) else df_copy
        grouped = lf.select(base_group_cols + value_cols)
        if base_group_cols:
            grouped = grouped.group_by(base_group_cols).agg(
                [pl.col(col).sum().alias(col) for col in value_cols]
            )
        else:
            grouped = grouped.select(
                [pl.col(col).sum().alias(col) for col in value_cols]
            )
        try:
            collected = grouped.collect(engine="streaming")
        except pl.exceptions.PolarsError:
            collected = grouped.collect()
        self.mekko_base_frames[base_key] = collected
        self.base_misses += 1
        return collected

    def get_mekko_grouped_frame(
        self,
        names: dict[str, str],
        column: str,
        small_multiples_column_array: list[str],
        value_cols: list[str],
        chart_dict: dict[str, Any],
        builder: Callable[..., pl.LazyFrame],
        df_copy: pl.DataFrame | pl.LazyFrame,
        family_dimensions: list[str] | None = None,
    ) -> pl.LazyFrame:
        """Return cached grouped Mekko data as a LazyFrame."""

        source_columns = self._columns(df_copy)
        target_group_cols, target_value_cols = self._target_mekko_columns(
            names,
            column,
            small_multiples_column_array,
            value_cols,
            chart_dict,
            source_columns,
        )
        key = ("grouped", tuple(target_group_cols), tuple(target_value_cols))
        cached = self.mekko_grouped_frames.get(key)
        if cached is not None:
            self.hits += 1
            return cached.lazy()

        base_group_cols = self._base_mekko_columns(
            names,
            target_group_cols,
            small_multiples_column_array,
            chart_dict,
            source_columns,
            family_dimensions,
        )
        if set(target_group_cols).issubset(base_group_cols):
            base = self._get_mekko_base_frame(
                df_copy, base_group_cols, target_value_cols
            )
            grouped = base.lazy()
            if target_group_cols:
                grouped = grouped.group_by(target_group_cols).agg(
                    [pl.col(col).sum().alias(col) for col in target_value_cols]
                )
            else:
                grouped = grouped.select(
                    [pl.col(col).sum().alias(col) for col in target_value_cols]
                )
        else:
            grouped = builder(
                df_copy,
                column,
                small_multiples_column_array,
                value_cols,
                chart_dict,
            )
        try:
            collected = grouped.collect(engine="streaming")
        except pl.exceptions.PolarsError:
            collected = grouped.collect()
        self.mekko_grouped_frames[key] = collected
        self.misses += 1
        return collected.lazy()


@dataclass(frozen=True)
class _PeriodWindowSelection:
    """Resolved date-window buckets for a comparison chart."""

    frame: pl.DataFrame
    selected_periods: list[str]
    audit: dict[str, Any]


class _DummyTab:
    def __enter__(self) -> "_DummyTab":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _LegacyCaptureNotifier:
    """Capture figures that the legacy UI code sends to Streamlit."""

    def __init__(self) -> None:
        self.figures: list[Any] = []
        self.events: list[dict[str, Any]] = []

    def tabs(self, labels: list[str]) -> list[_DummyTab]:
        self.events.append({"method": "tabs", "labels": list(labels)})
        return [_DummyTab() for _label in labels]

    def plotly_chart(self, fig: Any, **_kwargs: Any) -> None:
        self.figures.append(fig)

    def dataframe(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def notify(
        self,
        level: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "method": "notify",
                "level": level,
                "message": message,
                "context": context or {},
            }
        )

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def _noop(*args: Any, **_kwargs: Any) -> str:
            self.events.append(
                {"method": name, "args": [_safe_event_arg(arg) for arg in args[:3]]}
            )
            return ""

        return _noop


def _legacy_event_message(event: dict[str, Any]) -> str:
    """Return the display message carried by a captured legacy UI event."""

    message = event.get("message")
    if isinstance(message, str):
        return message
    args = event.get("args")
    if isinstance(args, list) and args:
        return str(args[0])
    return ""


def _is_small_multiple_total_warning(
    event: dict[str, Any], spec: dict[str, Any]
) -> bool:
    """Return whether a legacy error event is a non-blocking total check."""

    if not spec.get("small_multiples_dimension"):
        return False
    message = _legacy_event_message(event)
    return message.startswith(
        "Small multiples values and total values differ by "
    ) or message.startswith(("Small multiples total is", "Total is"))


def _safe_event_arg(value: Any) -> str:
    """Return a concise event argument without evaluating lazy query plans."""

    if isinstance(value, pl.LazyFrame):
        try:
            columns = value.collect_schema().names()
        except (pl.exceptions.PolarsError, TypeError, ValueError):
            columns = []
        return f"LazyFrame(columns={columns})"
    if isinstance(value, pl.DataFrame):
        return f"DataFrame(rows={value.height}, columns={value.columns})"
    return str(value)


def _safe_download_frame(value: Any) -> Any:
    """Return a frame safe for legacy data-export tabs."""

    if not isinstance(value, (pl.DataFrame, pl.LazyFrame)):
        return value
    try:
        columns = (
            value.columns
            if isinstance(value, pl.DataFrame)
            else value.collect_schema().names()
        )
        if len(columns) != len(set(columns)):
            return pl.DataFrame()
        if isinstance(value, pl.LazyFrame):
            value.select(pl.len()).collect()
    except (pl.exceptions.PolarsError, TypeError, ValueError):
        return pl.DataFrame()
    return value


def _is_polars_numeric_dtype(dtype: Any) -> bool:
    is_numeric = getattr(dtype, "is_numeric", None)
    return bool(is_numeric()) if callable(is_numeric) else False


def _is_stacked_bar_other_bucket_label(value: Any) -> bool:
    """Return whether a row label is a visual residual bucket."""

    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return (
        normalized in {"other", "others"}
        or normalized.startswith("other rank")
        or normalized.startswith("others rank")
        or normalized.startswith("all other")
    )


def _uses_local_stacked_bar_small_multiple_row_order(spec: dict[str, Any]) -> bool:
    """Return whether a stacked-bar small multiple should use local row ranking."""

    return spec.get("name") in {
        "bar_small_multiples",
        "stacked_bar_small_multiples",
        "related_metrics_bar_small_multiples",
    }


def _locally_order_stacked_bar_small_multiple_rows(
    frame: pl.DataFrame | pl.LazyFrame,
    chart_dict: dict[str, Any],
    names: dict[str, Any],
) -> pl.LazyFrame:
    """Drop padded rows and order one stacked-bar panel by its local total."""

    lf = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    schema = lf.collect_schema()
    columns = schema.names()
    x_dimension = str(chart_dict.get(names["xAxisDimension"]) or "")
    value_name = str(names["valueName"])
    numeric_columns = [
        column
        for column, dtype in schema.items()
        if column != x_dimension and _is_polars_numeric_dtype(dtype)
    ]
    if not numeric_columns:
        return lf

    signal_exprs = [pl.col(column).fill_null(0).abs() for column in numeric_columns]
    signal_expr = pl.sum_horizontal(signal_exprs)
    sort_source = (
        pl.col(value_name).fill_null(0).abs()
        if value_name in numeric_columns
        else signal_expr
    )
    sort_columns: list[str] = []
    sort_descending: list[bool] = []
    if x_dimension in columns:
        sort_columns.append("__mix_panel_sort_other_bucket")
        sort_descending.append(False)
        lf = lf.with_columns(
            pl.col(x_dimension)
            .cast(pl.Utf8)
            .fill_null("")
            .alias("__mix_panel_sort_label"),
            pl.col(x_dimension)
            .cast(pl.Utf8)
            .map_elements(
                lambda value: 0 if _is_stacked_bar_other_bucket_label(value) else 1,
                return_dtype=pl.Int8,
            )
            .alias("__mix_panel_sort_other_bucket"),
        )
    sort_columns.append("__mix_panel_sort_total")
    sort_descending.append(False)
    if x_dimension in columns:
        sort_columns.append("__mix_panel_sort_label")
        sort_descending.append(False)

    return (
        lf.filter(signal_expr > 1e-9)
        .with_columns(sort_source.alias("__mix_panel_sort_total"))
        .sort(sort_columns, descending=sort_descending)
        .drop(sort_columns)
    )


def _stacked_bar_small_multiple_panel_labels(fig: Any) -> dict[str, list[str]]:
    panel_labels: dict[str, list[str]] = {}
    for trace in _sequence(getattr(fig, "data", None)):
        if (
            str(getattr(trace, "name", "") or "")
            == STACKED_BAR_SMALL_MULTIPLE_AXIS_SPACER
        ):
            continue
        if str(getattr(trace, "type", "") or "") != "bar":
            continue
        if str(getattr(trace, "orientation", "") or "v").lower() != "h":
            continue
        axis_ref = str(getattr(trace, "yaxis", None) or "y")
        labels = panel_labels.setdefault(axis_ref, [])
        for value in _sequence(getattr(trace, "y", None)):
            if value is None:
                continue
            label = str(value)
            if not label.strip() or label in labels:
                continue
            labels.append(label)
    return panel_labels


def _stacked_bar_small_multiple_panel_row_counts(fig: Any) -> list[int]:
    return [
        len(labels)
        for labels in _stacked_bar_small_multiple_panel_labels(fig).values()
        if labels
    ]


def _layout_yaxis_name(axis_ref: str) -> str:
    if axis_ref == "y":
        return "yaxis"
    suffix = axis_ref[1:]
    return f"yaxis{suffix}" if suffix.isdigit() else "yaxis"


def _layout_xaxis_name(axis_ref: str) -> str:
    if axis_ref == "x":
        return "xaxis"
    suffix = axis_ref[1:]
    return f"xaxis{suffix}" if suffix.isdigit() else "xaxis"


def _matching_xaxis_ref_for_yaxis(axis_ref: str) -> str:
    if axis_ref == "y":
        return "x"
    suffix = axis_ref[1:]
    return f"x{suffix}" if suffix.isdigit() else "x"


def _remove_stacked_bar_small_multiple_axis_spacers(fig: Any) -> None:
    data = tuple(
        trace
        for trace in _sequence(getattr(fig, "data", None))
        if str(getattr(trace, "name", "") or "")
        != STACKED_BAR_SMALL_MULTIPLE_AXIS_SPACER
    )
    try:
        fig.data = data
    except (AttributeError, TypeError, ValueError):
        return


def _reserve_stacked_bar_small_multiple_category_slots(
    fig: Any, min_row_slots: int
) -> None:
    _remove_stacked_bar_small_multiple_axis_spacers(fig)
    panel_labels = _stacked_bar_small_multiple_panel_labels(fig)
    panel_row_counts = [len(labels) for labels in panel_labels.values() if labels]
    if not panel_row_counts:
        return
    max_panel_rows = max(max(panel_row_counts), min_row_slots)
    for axis_ref, labels in panel_labels.items():
        if not labels:
            continue
        padding_count = max(max_panel_rows - len(labels), 0)
        padding_labels = [" " * (index + 1) for index in range(padding_count)]
        axis = getattr(getattr(fig, "layout", None), _layout_yaxis_name(axis_ref), None)
        if axis is None:
            continue
        axis.update(
            matches=None,
            categoryorder="array",
            categoryarray=padding_labels + labels,
            tickmode="array",
            tickvals=labels,
            ticktext=labels,
            showticklabels=True,
            autorange=True,
        )
        if padding_labels:
            fig.add_trace(
                {
                    "type": "scatter",
                    "name": STACKED_BAR_SMALL_MULTIPLE_AXIS_SPACER,
                    "x": [0] * len(padding_labels),
                    "y": padding_labels,
                    "mode": "markers",
                    "marker": {"opacity": 0, "size": 1},
                    "showlegend": False,
                    "hoverinfo": "skip",
                    "xaxis": _matching_xaxis_ref_for_yaxis(axis_ref),
                    "yaxis": axis_ref,
                }
            )


def _apply_stacked_bar_small_multiple_readable_canvas(
    figures: list[Any], spec: dict[str, Any]
) -> None:
    """Keep locally sorted horizontal small multiples readable after padding removal."""

    if spec.get("name") != "stacked_bar_small_multiples":
        return
    for fig in figures:
        if not _has_horizontal_bar_trace(fig):
            continue
        columns, rows = _subplot_grid_size(fig)
        if columns * rows <= 1:
            continue
        panel_row_counts = _stacked_bar_small_multiple_panel_row_counts(fig)
        if not panel_row_counts:
            continue
        configured_min_slots = int(
            spec.get("small_multiple_min_row_slots")
            or spec.get("small_multiples_min_row_slots")
            or STACKED_BAR_SMALL_MULTIPLE_MIN_ROW_SLOTS
        )
        min_row_slots = max(
            STACKED_BAR_SMALL_MULTIPLE_MIN_ROW_SLOTS, configured_min_slots
        )
        _reserve_stacked_bar_small_multiple_category_slots(fig, min_row_slots)
        max_panel_rows = max(max(panel_row_counts), min_row_slots)
        layout = getattr(fig, "layout", None)
        current_width = int(getattr(layout, "width", 0) or 0)
        current_height = int(getattr(layout, "height", 0) or 0)
        panel_height = max(520, 170 + max_panel_rows * 40)
        target_width = max(current_width, columns * 1110)
        target_height = max(current_height, rows * panel_height)
        fig.update_layout(width=target_width, height=target_height)


def _is_barmekko_small_multiple_artifact(artifact_name: str | None) -> bool:
    if not artifact_name:
        return False
    return Path(artifact_name).stem.startswith("barmekko_small_multiples")


def _apply_barmekko_small_multiple_label_canvas(
    figures: list[Any], spec: dict[str, Any]
) -> None:
    """Reserve space for right-edge value labels in barmekko small multiples."""

    if spec.get("name") != "barmekko_small_multiples":
        return
    for fig in figures:
        if not _has_horizontal_bar_trace(fig):
            continue
        columns, rows = _subplot_grid_size(fig)
        if columns * rows <= 1:
            continue
        maxima_by_xaxis: dict[str, float] = {}
        for trace in _sequence(getattr(fig, "data", None)):
            if str(getattr(trace, "type", "") or "") != "bar":
                continue
            if str(getattr(trace, "orientation", "") or "v").lower() != "h":
                continue
            values: list[float] = []
            for value in _sequence(getattr(trace, "x", None)):
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    continue
            if not values:
                continue
            xaxis_ref = str(getattr(trace, "xaxis", None) or "x")
            maxima_by_xaxis[xaxis_ref] = max(
                maxima_by_xaxis.get(xaxis_ref, 0.0), max(values)
            )
        for xaxis_ref, maximum in maxima_by_xaxis.items():
            if maximum <= 0:
                continue
            axis_name = _layout_xaxis_name(xaxis_ref)
            axis = getattr(fig.layout, axis_name, None)
            if axis is not None:
                axis.update(
                    range=[0, maximum * BARMEEKKO_SMALL_MULTIPLE_LABEL_RANGE_PADDING],
                    autorange=False,
                )
        layout = getattr(fig, "layout", None)
        current_width = int(getattr(layout, "width", 0) or 0)
        current_height = int(getattr(layout, "height", 0) or 0)
        current_margin = (
            fig.layout.margin.to_plotly_json()
            if getattr(fig.layout, "margin", None)
            else {}
        )
        current_margin["r"] = max(
            int(current_margin.get("r") or 0), BARMEEKKO_SMALL_MULTIPLE_RIGHT_MARGIN
        )
        fig.update_layout(
            width=max(current_width, BARMEEKKO_SMALL_MULTIPLE_MIN_WIDTH),
            height=max(current_height, BARMEEKKO_SMALL_MULTIPLE_MIN_HEIGHT),
            margin=current_margin,
        )


def _legacy_import_parent() -> Path:
    """Return shared plugin modules in dev, otherwise packaged vendor modules."""

    if (SHARED_VENDOR_ROOT / "modules" / "__init__.py").exists():
        return SHARED_VENDOR_ROOT
    return VENDOR_ROOT


def _ensure_legacy_import_path() -> None:
    legacy_parent = _legacy_import_parent()
    _prepare_legacy_import_parent(legacy_parent)
    _install_polars_headless_compat()


def _install_polars_headless_compat() -> None:
    """Install tiny compatibility shims needed by the vendored chart code."""

    if not hasattr(pl.LazyFrame, "get_column"):

        def _get_column(self: pl.LazyFrame, column: str) -> pl.Series:
            return (
                self.select(pl.col(column))
                .collect(engine="streaming")
                .get_column(column)
            )

        pl.LazyFrame.get_column = _get_column  # type: ignore[attr-defined]


def cleanup_legacy_imports() -> None:
    """Remove shared/vendored ``modules`` imports loaded by this plugin."""

    module_roots = [
        (SHARED_VENDOR_ROOT / "modules").resolve(),
        (VENDOR_ROOT / "modules").resolve(),
    ]
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            module_path = Path(module_file).resolve() if module_file else None
            if module_path and any(
                module_path.is_relative_to(root) for root in module_roots
            ):
                del sys.modules[name]
    for vendor in (str(SHARED_VENDOR_ROOT), str(VENDOR_ROOT)):
        while vendor in sys.path:
            sys.path.remove(vendor)


@contextlib.contextmanager
def _capture_legacy_ui() -> Any:
    _ensure_legacy_import_path()
    from modules.utilities.ui_notifier import use_ui_notifier

    notifier = _LegacyCaptureNotifier()
    with use_ui_notifier(notifier):
        yield notifier


def _put_if_key(
    target: dict[str, Any], names: dict[str, str], key: str, value: Any
) -> None:
    if key in names:
        target[names[key]] = value


def _legacy_value_label_mode(names: dict[str, str], spec: dict[str, Any]) -> str:
    """Return the legacy value-label choice for the chart spec."""

    fallback = names["percentOfTotal"] if spec.get("share_view") else names["absolute"]
    mode = spec.get("value_label_mode")
    if not mode:
        return fallback
    options = {
        "absolute": names["absolute"],
        names["absolute"]: names["absolute"],
        "percent_total": names["percentOfTotal"],
        names["percentOfTotal"]: names["percentOfTotal"],
        "percent_row_total": names["percentOfRowTotal"],
        names["percentOfRowTotal"]: names["percentOfRowTotal"],
        "percent_column_total": names["percentOfColumnTotal"],
        names["percentOfColumnTotal"]: names["percentOfColumnTotal"],
    }
    try:
        return options[str(mode)]
    except KeyError as exc:
        raise ValueError(f"Unsupported legacy value label mode: {mode}") from exc


def _legacy_show_legend_mode(names: dict[str, str], spec: dict[str, Any]) -> str:
    """Return the legacy legend-label placement choice for the chart spec."""

    legacy_chart_key = str(spec["legacy_chart_key"])
    fallback = (
        names["showLegendOnTop"]
        if legacy_chart_key == "marimekkoChart"
        else names["showLegendLeftOrRight"]
    )
    mode = spec.get("show_legend_mode")
    if not mode:
        return fallback
    options = {
        "both": names["showBoth"],
        names["showBoth"]: names["showBoth"],
        "inside": names["showLegendInBars"],
        "inside_bars": names["showLegendInBars"],
        names["showLegendInBars"]: names["showLegendInBars"],
        "left_right": names["showLegendLeftOrRight"],
        names["showLegendLeftOrRight"]: names["showLegendLeftOrRight"],
        "top": names["showLegendOnTop"],
        "top_only": names["showLegendOnTop"],
        names["showLegendOnTop"]: names["showLegendOnTop"],
    }
    try:
        return options[str(mode)]
    except KeyError as exc:
        raise ValueError(f"Unsupported legacy legend label mode: {mode}") from exc


def _legacy_period_choice(names: dict[str, str], spec: dict[str, Any]) -> str:
    """Return the legacy period-grain label for chart positioning rules."""

    period_grain = str(spec.get("period_grain") or "").strip().lower()
    choices = {
        "year": names["yearName"],
        "quarter": names["quarterName"],
        "month": names["monthName"],
        "week": names["weekName"],
    }
    return choices.get(period_grain, names["monthName"])


def _legacy_chart_dict(
    names: dict[str, str],
    spec: dict[str, Any],
    *,
    metric: str,
    currency: str,
) -> dict[str, Any]:
    max_items = int(spec.get("max_items") or 12)
    small_multiples_dimension = spec.get("small_multiples_dimension")
    dimension_panel_chart = bool(
        spec.get("dimension_panel_chart") or spec.get("dimension_panel_small_multiples")
    )
    dimensions = [str(item) for item in spec.get("dimensions") or [] if item]
    metrics = [str(item) for item in spec.get("metrics") or [metric] if item]
    x_metric = str(spec.get("x_metric") or metric)
    y_metric = str(spec.get("y_metric") or metric)
    multiplied_metric = str(spec.get("multiplied_metric") or f"{x_metric} x {y_metric}")
    selected_periods = [
        str(item) for item in spec.get("selected_periods") or [CURRENT_PERIOD] if item
    ]
    to_plot_period = selected_periods[-1] if selected_periods else CURRENT_PERIOD
    if "x_dimension" in spec:
        x_dimension = spec.get("x_dimension")
    else:
        x_dimension = dimensions[0] if dimensions else ""
    if "y_dimension" in spec:
        y_dimension = spec.get("y_dimension")
    else:
        y_dimension = dimensions[1] if len(dimensions) > 1 else ""
    primary_dimension = str(x_dimension or "")
    secondary_dimension = str(y_dimension or "")
    count_dimension = str(spec.get("count_dimension") or primary_dimension or "")
    aggregate_uniques_by_dimension = spec.get("aggregate_uniques_by_dimension")
    if aggregate_uniques_by_dimension is None:
        aggregate_uniques_by_dimension = bool(secondary_dimension)
    aggregate_uniques_dimension = str(
        spec.get("aggregate_uniques_dimension")
        or secondary_dimension
        or primary_dimension
        or ""
    )
    nothing = names["nothingFilteredName"]
    met = names["metConditionValue"]
    not_met = names["notMetConditionValue"]
    aggregate_other_items = bool(spec.get("aggregate_other_items", True))

    def axis_config(axis: str) -> dict[str, Any]:
        axis_lower = axis.lower()
        return {
            names["numberOfTop"]: int(spec.get(f"{axis_lower}_max_items") or max_items),
            names["aggregateOtherItems"]: bool(
                spec.get(f"{axis_lower}_aggregate_other_items", aggregate_other_items)
            ),
        }

    x_axis = axis_config("X")
    y_axis = axis_config("Y")
    w_axis = axis_config("W")
    small_multiples_panel_count = 0
    if small_multiples_dimension or dimension_panel_chart:
        small_multiples_panel_count = max(
            2,
            int(
                spec.get("small_multiples_max_panels")
                or (len(dimensions) if dimension_panel_chart else min(max_items, 6))
            ),
        )
        panel_axis = str(spec.get("small_multiples_panel_axis") or "Y").upper()
        panel_number_of_top = max(small_multiples_panel_count - 1, 1)
        panel_axis_config = {
            "X": x_axis,
            "Y": y_axis,
            "W": w_axis,
        }.get(panel_axis, y_axis)
        panel_axis_config[names["numberOfTop"]] = panel_number_of_top
        panel_axis_config[names["aggregateOtherItems"]] = True
    plot_values_as = (
        names["percentOfResultRow"] if spec.get("share_view") else names["absolute"]
    )
    show_values_as = _legacy_value_label_mode(names, spec)
    show_legend = _legacy_show_legend_mode(names, spec)
    metrics_to_show_in_data_column = [
        str(item) for item in spec.get("metrics_to_show_in_data_column") or [] if item
    ]
    show_metrics_in_data_column = bool(
        spec.get("show_metrics_in_data_column") and metrics_to_show_in_data_column
    )
    period_choice = _legacy_period_choice(names, spec)
    show_only = str(spec.get("show_only") or names["showTop"])
    legacy_chart_key = str(spec["legacy_chart_key"])
    legacy_y_dimension = secondary_dimension or nothing
    if (
        legacy_chart_key == "stackedParetoChart"
        and not secondary_dimension
        and primary_dimension
    ):
        # The stacked Pareto ABC view has no parent dimension, but the legacy
        # renderer still needs a real dimension here so it keeps the A/B/C class
        # columns instead of falling back to the metadata Value column.
        legacy_y_dimension = primary_dimension
    cagr_metric_names = metrics if bool(spec.get("show_cagr", False)) else []
    palette_key = "bainColorpalette"
    sort_axis = str(spec.get("sort_axis") or "")
    if sort_axis in {"area", names["areaSort"]}:
        sort_axis = names["areaSort"]
    elif sort_axis in {"width", names["xAxisSort"]}:
        sort_axis = names["xAxisSort"]
    elif sort_axis in {"length", names["yAxisSort"]}:
        sort_axis = names["yAxisSort"]
    elif legacy_chart_key == "barmekkoChart":
        sort_axis = names["areaSort"]
    else:
        sort_axis = names["yAxisSort"]
    chart = {
        names["chosenChart"]: names[legacy_chart_key],
        names["selectedPeriods"]: selected_periods,
        names["toPlotPeriod"]: to_plot_period,
        names["plotSmallMultiplesOtherCharts"]: bool(
            small_multiples_dimension or dimension_panel_chart
        ),
        names["smallMultiplesColumn"]: small_multiples_dimension or nothing,
        names["numberOfPlottedSmallMultiples"]: (
            small_multiples_panel_count if small_multiples_dimension else 0
        ),
        names["colorChoice"]: names["redToGreen"],
        names["colorpalette"]: names[palette_key],
        names["compareScenariosOrPeriods"]: names["comparePeriods"],
        names["filterDates"]: False,
        names["shareOfTotalMarket"]: False,
        names["varianceInPercent"]: False,
        names["plotAsBaseline"]: False,
        names["plotValuesAsChoice"]: plot_values_as,
        names["showValuesAs"]: show_values_as,
        names["rowToPlotName"]: names["entireDatasetName"],
        names["metricsToPlot"]: metrics,
        names["stackedColumnMetric"]: metrics[0],
        names["singleMetric"]: y_metric,
        names["xAxisMetric"]: x_metric,
        names["yAxisMetric"]: y_metric,
        names["multipliedMetric"]: multiplied_metric,
        names["sortAxis"]: sort_axis,
        names["xAxisDimension"]: primary_dimension or nothing,
        names["yAxisDimension"]: legacy_y_dimension,
        names["selectDimensionsToPlot"]: dimensions,
        names["mainDimension"]: dimensions[:1],
        names["countColumn"]: count_dimension or nothing,
        names["countByColumn"]: count_dimension or nothing,
        names["aggregateUniquesByDimension"]: bool(aggregate_uniques_by_dimension),
        names["aggregateUniquesDimension"]: aggregate_uniques_dimension or nothing,
        names["showOnly"]: show_only,
        names["periodChoice"]: period_choice,
        names["canPlotYearToYear"]: True,
        names["setTimePeriodTabLabel"]: names["comparePeriods"],
        names["processingChoice"]: names["runOneDimensionalAnalysis"],
        names["varianceAnalysisChart"]: not_met,
        names["currencyChoice"]: currency,
        names["fullCurrencyName"]: currency,
        "X": x_axis,
        "Y": y_axis,
        "W": w_axis,
    }
    dimension_display_labels = spec.get("dimension_display_labels")
    if isinstance(dimension_display_labels, dict) and dimension_display_labels:
        chart["dimension_display_labels"] = {
            str(key): str(value)
            for key, value in dimension_display_labels.items()
            if str(key).strip() and str(value).strip()
        }
    for optional_key, value in (
        ("datePeriodName", period_choice),
        ("periodToDate", bool(spec.get("period_to_date", False))),
        ("compareWithYearBefore", bool(spec.get("rolling_comparison", False))),
        ("mostRecentPeriod", int(spec.get("most_recent_period", -1))),
        ("prepareFileForDownload", False),
        ("plotSmallMultiplesWaterfall", False),
        ("showInitialAndFinalValues", True),
        ("countMetricsAvgArray", []),
        ("countMetricsSumArray", cagr_metric_names),
        ("showMetricsInDataColumn", show_metrics_in_data_column),
        ("metricsToShowInDataColumn", metrics_to_show_in_data_column),
        ("numberOfMetricsInDataColumn", len(metrics_to_show_in_data_column)),
        ("plotOverlayChart", bool(spec.get("plot_overlay_chart", False))),
        ("highlightOverlayChart", bool(spec.get("highlight_overlay_chart", False))),
        ("plotTotalBubble", False),
        ("resampleDates", 1),
        ("chartSubType", names["absolute"]),
        ("summaryStackedColumnChart", False),
        ("highlightValue", not_met),
        ("plotCommentText", []),
        ("showCAGR", bool(spec.get("show_cagr", False))),
        ("showLegend", show_legend),
        ("showAbsoluteValues", bool(spec.get("show_absolute_values", True))),
        ("showAverageValueName", bool(spec.get("show_average_value", False))),
        ("showRank", bool(spec.get("show_rank", True))),
        ("fatherAndChildDimensions", False),
        ("showTopForEachItem", bool(spec.get("show_top_for_each_item", False))),
        ("chosenCohortColumn", spec.get("chosen_cohort_column")),
        ("lostAndDroppedColumn", spec.get("lost_and_dropped_column")),
    ):
        if value is not None:
            _put_if_key(chart, names, optional_key, value)
    if spec.get("focus_status") == "resolved" and spec.get("focus_item"):
        chart[names["highlightedDimension"]] = [str(spec["focus_item"])][
            :FOCUS_ITEM_HIGHLIGHT_MAX_ITEMS
        ]
        if (
            legacy_chart_key == "timelineChart"
            and not dimensions
            and spec.get("focus_dimension")
        ):
            chart[names["selectDimensionsToPlot"]] = [str(spec["focus_dimension"])]
    if met and (small_multiples_dimension or dimension_panel_chart):
        chart[names["plotSmallMultiplesOtherCharts"]] = met
    if dimension_panel_chart:
        chart.pop(names["xAxisDimension"], None)
        chart.pop(names["yAxisDimension"], None)
        chart[names["aggregateUniquesByDimension"]] = False
        chart[names["aggregateUniquesDimension"]] = nothing
    if spec.get("related_metrics_bar"):
        # Legacy growth overlays are selected through metricsToPlot[1].
        # Keeping the generic metric keys would make get_growth_rate inspect
        # Sales/Sales instead and skip the overlay metric calculation.
        chart.pop(names["xAxisMetric"], None)
        chart.pop(names["yAxisMetric"], None)
        chart.pop(names["singleMetric"], None)
    return chart


def _legacy_param_dict(
    names: dict[str, str],
    *,
    total: float,
    selected_periods: list[str],
    period_totals: dict[str, float],
    columns: list[str],
    least_recent_date: date | None = None,
    most_recent_date: date | None = None,
    date_period_choice: str | None = None,
) -> dict[str, Any]:
    not_met = names["notMetConditionValue"]
    today = date.today()
    least_recent_date = least_recent_date or today
    most_recent_date = most_recent_date or today
    period_zero = selected_periods[0] if selected_periods else CURRENT_PERIOD
    period_one = selected_periods[-1] if selected_periods else CURRENT_PERIOD
    period_zero_total = period_totals.get(period_zero, 0.0)
    period_one_total = period_totals.get(period_one, total)
    param = {
        names["columnHash"]: {},
        names["mostRecentDate"]: most_recent_date,
        names["leastRecentDate"]: least_recent_date,
        names["periodLengthInMonths"]: 12,
        names["fileUploadDisabled"]: True,
        names["renameTitlesDict"]: {},
        names["isFilteredKey"]: not_met,
        names["numberOfPeriodsFound"]: len(selected_periods) or 1,
        names["impossibleToProcessFile"]: False,
        names["dropLowCorrelationCols"]: False,
        names["toTitleCase"]: False,
        names["reverseSortPeriods"]: False,
        names["isColumnMultiplied"]: False,
        names["allPeriodsList"]: selected_periods or [CURRENT_PERIOD],
        names["selectedPeriods"]: selected_periods or [CURRENT_PERIOD],
        names["totalAmountPeriodZero"]: period_zero_total,
        names["totalAmountPeriodOne"]: period_one_total,
        names["totalVarianceValue"]: period_one_total - period_zero_total,
        names["totalAmountPeriodZeroFiltered"]: period_zero_total,
        names["totalAmountPeriodOneFiltered"]: period_one_total,
        names["periodZeroSum"]: period_zero_total,
        names["periodOneSum"]: period_one_total,
    }
    flag_columns = {
        "unitsColFound": "unitsName",
        "volumeColFound": "volumeName",
        "discountColFound": "discountName",
        "marginColFound": "marginName",
        "cogsColFound": "cogsName",
        "monetaryLocalCurrencyColFound": "monetaryLocalCurrencyName",
    }
    for flag, column_key in flag_columns.items():
        _put_if_key(param, names, flag, names[column_key] in columns)
    _put_if_key(
        param, names, "datePeriodName", date_period_choice or names["monthName"]
    )
    return param


def _drop_existing_columns(frame: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    """Drop columns that legacy cohort derivation is about to recreate."""

    existing = [column for column in columns if column in frame.columns]
    if not existing:
        return frame
    return frame.drop(existing)


def _ordered_periods(names: dict[str, str], param: dict[str, Any]) -> list[str]:
    """Return legacy selected periods as strings in their configured order."""

    return [str(period) for period in param.get(names["allPeriodsList"], [])]


def _period_values_from_frame(frame: pl.DataFrame, period_name: str) -> list[str]:
    """Return period values in a deterministic display order."""

    if period_name not in frame.columns:
        return []
    values = [
        str(value)
        for value in frame.select(pl.col(period_name).cast(pl.Utf8)).to_series()
        if value is not None
    ]
    values = list(dict.fromkeys(values))
    if all(_period_sort_key(value)[0] == 0 for value in values):
        values = sorted(values, key=_period_sort_key)
    return values


def _latest_period_values_by_date(
    frame: pl.DataFrame,
    period_name: str,
    date_name: str,
    count: int,
) -> list[str]:
    """Return converted period labels ordered by their latest source date."""

    if count <= 0 or period_name not in frame.columns or date_name not in frame.columns:
        return []
    period_dates = (
        frame.group_by(period_name)
        .agg(pl.col(date_name).cast(pl.Date).max().alias("__max_date"))
        .sort(["__max_date", period_name])
        .tail(count)
    )
    return [
        str(value)
        for value in period_dates.get_column(period_name).to_list()
        if value is not None
    ]


def _period_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _cohort_visible_periods(
    periods: list[str],
    spec: dict[str, Any],
    fallback_periods: list[str],
) -> list[str]:
    visible = [str(period) for period in spec.get("cohort_visible_periods") or []]
    if visible:
        return visible
    raw_count = spec.get("cohort_visible_period_count") or 3
    try:
        visible_count = max(1, int(raw_count))
    except (TypeError, ValueError):
        visible_count = 3
    current = (
        visible[-1]
        if visible
        else (
            str(fallback_periods[-1])
            if fallback_periods
            else (periods[-1] if periods else CURRENT_PERIOD)
        )
    )
    if current in periods:
        end_index = periods.index(current) + 1
    else:
        end_index = len(periods)
    start_index = max(0, end_index - visible_count)
    return periods[start_index:end_index]


def _cohort_presence_frame(
    frame: pl.DataFrame,
    source_column: str,
    period_name: str,
    activity_metric: str | None,
    periods: list[str],
) -> pl.DataFrame:
    """Return active source/period pairs for cohort derivation."""

    presence = (
        frame.select(
            [
                source_column,
                period_name,
                *([activity_metric] if activity_metric else []),
            ]
        )
        .with_columns(pl.col(period_name).cast(pl.Utf8))
        .filter(pl.col(period_name).is_in(periods))
    )
    if activity_metric and activity_metric in presence.columns:
        presence = presence.filter(pl.col(activity_metric).fill_null(0) > 0)
    return presence.select([source_column, period_name]).unique()


def _cohort_activity_summary(
    frame: pl.DataFrame,
    source_column: str,
    period_name: str,
    activity_metric: str | None,
    periods: list[str],
    current_period: str,
) -> pl.DataFrame:
    """Summarize first/last/current activity for mechanical cohort labels."""

    period_order = pl.DataFrame(
        {period_name: periods, "__legacy_period_rank": list(range(len(periods)))}
    )
    presence = _cohort_presence_frame(
        frame,
        source_column,
        period_name,
        activity_metric,
        periods,
    ).join(period_order, on=period_name, how="left")
    entities = frame.select(source_column).unique()
    if presence.is_empty():
        return entities.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("__legacy_first_active_period"),
            pl.lit(None, dtype=pl.Int64).alias("__legacy_first_active_rank"),
            pl.lit(None, dtype=pl.Utf8).alias("__legacy_last_active_period"),
            pl.lit(None, dtype=pl.Int64).alias("__legacy_last_active_rank"),
            pl.lit(False).alias("__legacy_has_current"),
        )
    summary = presence.group_by(source_column).agg(
        [
            pl.col(period_name)
            .sort_by(pl.col("__legacy_period_rank"))
            .first()
            .alias("__legacy_first_active_period"),
            pl.col("__legacy_period_rank").min().alias("__legacy_first_active_rank"),
            pl.col(period_name)
            .sort_by(pl.col("__legacy_period_rank"))
            .last()
            .alias("__legacy_last_active_period"),
            pl.col("__legacy_period_rank").max().alias("__legacy_last_active_rank"),
            (pl.col(period_name) == current_period).any().alias("__legacy_has_current"),
        ]
    )
    return entities.join(summary, on=source_column, how="left").with_columns(
        pl.col("__legacy_has_current").fill_null(False)
    )


def _legacy_since_label_expr(
    names: dict[str, str], visible_periods: list[str], older_cutoff_rank: int
) -> pl.Expr:
    prefix = f"{names['sinceName']} "
    expr = pl.when(pl.col("__legacy_first_active_period").is_null()).then(pl.lit(""))
    if visible_periods and older_cutoff_rank > 0:
        expr = expr.when(pl.col("__legacy_first_active_rank") < older_cutoff_rank).then(
            pl.lit(f"Before {visible_periods[0]}")
        )
    return expr.otherwise(
        pl.lit(prefix) + pl.col("__legacy_first_active_period").cast(pl.Utf8)
    )


def _legacy_lost_label_expr(
    names: dict[str, str], visible_periods: list[str], older_cutoff_rank: int
) -> pl.Expr:
    after_prefix = f"{names['lostName']} after "
    expr = (
        pl.when(pl.col("__legacy_has_current"))
        .then(pl.lit(names["activeName"]))
        .when(pl.col("__legacy_last_active_period").is_null())
        .then(pl.lit(names["activeName"]))
    )
    if visible_periods and older_cutoff_rank > 0:
        expr = expr.when(pl.col("__legacy_last_active_rank") < older_cutoff_rank).then(
            pl.lit(f"{names['lostName']} before {visible_periods[0]}")
        )
    return expr.otherwise(
        pl.lit(after_prefix) + pl.col("__legacy_last_active_period").cast(pl.Utf8)
    )


def _drop_legacy_cohort_helpers(frame: pl.DataFrame) -> pl.DataFrame:
    return _drop_existing_columns(
        frame,
        [
            "__legacy_first_active_period",
            "__legacy_first_active_rank",
            "__legacy_last_active_period",
            "__legacy_last_active_rank",
            "__legacy_has_current",
        ],
    )


def _add_legacy_since_column(
    frame: pl.DataFrame,
    names: dict[str, str],
    param: dict[str, Any],
    source_column: str,
    activity_metric: str | None = None,
    spec: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Match legacy ``add_cohort_column`` for headless chart rendering."""

    period_name = names["periodName"]
    selected_periods = _ordered_periods(names, param)
    periods = _period_values_from_frame(frame, period_name) or selected_periods
    visible_periods = _cohort_visible_periods(periods, spec or {}, selected_periods)
    current_period = (
        visible_periods[-1] if visible_periods else (periods[-1] if periods else "")
    )
    older_cutoff_rank = periods.index(visible_periods[0]) if visible_periods else 0
    cohort_column = f"{source_column}{names['chosenCohortSuffix']}"
    result = _drop_existing_columns(frame, [cohort_column])
    if (
        source_column not in result.columns
        or period_name not in result.columns
        or not periods
    ):
        return result
    cohorts = _cohort_activity_summary(
        result,
        source_column,
        period_name,
        activity_metric,
        periods,
        current_period,
    ).with_columns(
        _legacy_since_label_expr(names, visible_periods, older_cutoff_rank).alias(
            cohort_column
        )
    )
    cohorts = _drop_legacy_cohort_helpers(cohorts).select(
        [source_column, cohort_column]
    )
    return result.join(cohorts, on=source_column, how="left")


def _add_legacy_lost_column(
    frame: pl.DataFrame,
    names: dict[str, str],
    param: dict[str, Any],
    source_column: str,
    activity_metric: str | None = None,
    spec: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Match legacy ``add_lost_and_dropped_column`` for headless chart rendering."""

    period_name = names["periodName"]
    selected_periods = _ordered_periods(names, param)
    periods = _period_values_from_frame(frame, period_name) or selected_periods
    visible_periods = _cohort_visible_periods(periods, spec or {}, selected_periods)
    current_period = (
        visible_periods[-1] if visible_periods else (periods[-1] if periods else "")
    )
    older_cutoff_rank = periods.index(visible_periods[0]) if visible_periods else 0
    lost_column = f"{source_column}{names['lostAndDroppedSuffix']}"
    result = _drop_existing_columns(frame, [lost_column])
    if (
        source_column not in result.columns
        or period_name not in result.columns
        or len(periods) < 2
    ):
        return result
    lost = _cohort_activity_summary(
        result,
        source_column,
        period_name,
        activity_metric,
        periods,
        current_period,
    ).with_columns(
        _legacy_lost_label_expr(names, visible_periods, older_cutoff_rank).alias(
            lost_column
        )
    )
    lost = _drop_legacy_cohort_helpers(lost).select([source_column, lost_column])
    return result.join(lost, on=source_column, how="left")


def _apply_legacy_cohort_columns(
    frame: pl.DataFrame,
    names: dict[str, str],
    param: dict[str, Any],
    chart: dict[str, Any],
    spec: dict[str, Any],
) -> pl.DataFrame:
    """Derive since/lost columns with the legacy cohort logic."""

    chosen_source = spec.get("chosen_cohort_column")
    lost_source = spec.get("lost_and_dropped_column")
    if not chosen_source and not lost_source:
        return frame

    result = frame
    activity_metric = spec.get("cohort_activity_metric") or spec.get("metric")
    if chosen_source:
        cohort_column = str(
            spec.get("cohort_dimension")
            or f"{chosen_source}{names['chosenCohortSuffix']}"
        )
        if cohort_column not in result.columns:
            result = _add_legacy_since_column(
                result,
                names,
                param,
                str(chosen_source),
                str(activity_metric) if activity_metric else None,
                spec,
            )
    if lost_source:
        cohort_column = str(
            spec.get("cohort_dimension")
            or f"{lost_source}{names['lostAndDroppedSuffix']}"
        )
        if cohort_column not in result.columns:
            result = _add_legacy_lost_column(
                result,
                names,
                param,
                str(lost_source),
                str(activity_metric) if activity_metric else None,
                spec,
            )
    return result


def _coerce_date_bound(value: Any, fallback: date) -> date:
    """Return a plain date for legacy period-length calculations."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return fallback


def _canonical_date_bounds(frame: pl.DataFrame) -> tuple[date, date]:
    """Return min/max canonical dates for legacy time-based chart prep."""

    today = date.today()
    if CANONICAL_DATE not in frame.columns:
        return today, today
    bounds = frame.select(
        pl.col(CANONICAL_DATE).min().alias("least"),
        pl.col(CANONICAL_DATE).max().alias("most"),
    ).row(0, named=True)
    return (
        _coerce_date_bound(bounds.get("least"), today),
        _coerce_date_bound(bounds.get("most"), today),
    )


def _frame_for_spec_period_grain(
    canonical: pl.DataFrame,
    spec: dict[str, Any],
) -> pl.DataFrame:
    """Return a chart frame with spec-specific period grain applied."""

    period_grain = str(spec.get("period_grain") or "").strip().lower()
    if period_grain != "year" or CANONICAL_DATE not in canonical.columns:
        return canonical
    return canonical.with_columns(
        pl.col(CANONICAL_DATE)
        .dt.year()
        .cast(pl.Int64)
        .cast(pl.Utf8)
        .alias(CANONICAL_PERIOD)
    )


def _period_labels_look_like_raw_dates(values: Sequence[str]) -> bool:
    """Return whether period labels are raw date values needing legacy bucketing."""

    if not values:
        return False
    sample = [str(value) for value in values[: min(len(values), 20)]]
    parsed = 0
    for value in sample:
        try:
            datetime.fromisoformat(value)
        except ValueError:
            continue
        parsed += 1
    return parsed >= max(1, len(sample) // 2)


def _add_months(value: date, months: int) -> date:
    """Return ``value`` shifted by whole months, clamping invalid month days."""

    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_years(value: date, years: int) -> date:
    """Return ``value`` shifted by whole years, clamping leap-day dates."""

    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, month=2, day=28)


def _legacy_year_label(year: int) -> str:
    """Return the legacy IBCS-style two-digit year label."""

    return f"’{str(year)[-2:]}"


def _period_window_label(symbol: str, end_date: date) -> str:
    """Return legacy YTD/rolling labels with an explicit month cutoff."""

    return f"{symbol}{end_date.strftime('%b-%Y')}"


def _period_window_axis_year_label(value: Any) -> str | None:
    """Return a compact year label for visible period-window axis ticks."""

    text = _strip_plotly_html(value).strip()
    match = re.fullmatch(r"[_~][A-Za-z]{3}-(\d{4})", text)
    return match.group(1) if match else None


def _unique_canonical_dates(frame: pl.DataFrame) -> list[date]:
    """Return unique canonical dates as plain ``date`` values."""

    if CANONICAL_DATE not in frame.columns:
        return []
    values = (
        frame.select(pl.col(CANONICAL_DATE).cast(pl.Date).drop_nulls().unique().sort())
        .to_series()
        .to_list()
    )
    return [_coerce_date_bound(value, date.today()) for value in values]


def _year_extents(dates: Sequence[date]) -> dict[int, tuple[date, date]]:
    """Return first and last observed date by calendar year."""

    extents: dict[int, tuple[date, date]] = {}
    for value in dates:
        current = extents.get(value.year)
        if current is None:
            extents[value.year] = (value, value)
        else:
            extents[value.year] = (min(current[0], value), max(current[1], value))
    return extents


def _observed_year_is_complete(
    extents: dict[int, tuple[date, date]], year: int
) -> bool:
    """Return whether a year has observed January and December rows."""

    bounds = extents.get(year)
    if bounds is None:
        return False
    first, last = bounds
    return first.month == 1 and last.month == 12


def _observed_date_grain(dates: Sequence[date]) -> str:
    """Return the coarsest useful observed date grain for YTD matching."""

    ordered = sorted(dates)
    if len(ordered) < 2:
        return "unknown"
    gaps = [
        (later - earlier).days
        for earlier, later in zip(ordered, ordered[1:])
        if later > earlier
    ]
    if not gaps:
        return "unknown"
    smallest_gap = min(gaps)
    if smallest_gap <= 2:
        return "daily"
    if smallest_gap <= 8:
        return "weekly"
    return "periodic"


def _period_counts(frame: pl.DataFrame) -> dict[str, int]:
    """Return row counts by resolved period label."""

    if CANONICAL_PERIOD not in frame.columns or frame.is_empty():
        return {}
    return {
        str(row[CANONICAL_PERIOD]): int(row["len"] or 0)
        for row in frame.group_by(CANONICAL_PERIOD).len().to_dicts()
    }


def _period_window_frame_for_dates(
    canonical: pl.DataFrame,
    *,
    baseline_label: str | None,
    baseline_dates: Sequence[date],
    comparison_label: str,
    comparison_dates: Sequence[date],
) -> pl.DataFrame:
    """Return rows relabelled into explicit baseline/comparison date buckets."""

    date_expr = pl.col(CANONICAL_DATE).cast(pl.Date)
    label_expr = pl.when(date_expr.is_in(list(comparison_dates))).then(
        pl.lit(comparison_label)
    )
    if baseline_label and baseline_dates:
        label_expr = label_expr.when(date_expr.is_in(list(baseline_dates))).then(
            pl.lit(baseline_label)
        )
    return (
        canonical.with_columns(label_expr.otherwise(None).alias(CANONICAL_PERIOD))
        .filter(pl.col(CANONICAL_PERIOD).is_not_null())
        .sort([CANONICAL_PERIOD, CANONICAL_DATE])
    )


def _period_window_frame_for_ranges(
    canonical: pl.DataFrame,
    *,
    baseline_label: str | None,
    baseline_start: date | None,
    baseline_end: date | None,
    comparison_label: str,
    comparison_start: date,
    comparison_end: date,
) -> pl.DataFrame:
    """Return rows relabelled into explicit inclusive date-range buckets."""

    date_expr = pl.col(CANONICAL_DATE).cast(pl.Date)
    label_expr = pl.when(
        (date_expr >= pl.lit(comparison_start)) & (date_expr <= pl.lit(comparison_end))
    ).then(pl.lit(comparison_label))
    if baseline_label and baseline_start and baseline_end:
        label_expr = label_expr.when(
            (date_expr >= pl.lit(baseline_start)) & (date_expr <= pl.lit(baseline_end))
        ).then(pl.lit(baseline_label))
    return (
        canonical.with_columns(label_expr.otherwise(None).alias(CANONICAL_PERIOD))
        .filter(pl.col(CANONICAL_PERIOD).is_not_null())
        .sort([CANONICAL_PERIOD, CANONICAL_DATE])
    )


def _period_window_frame_for_years(
    canonical: pl.DataFrame,
    selected_years: Sequence[int],
) -> pl.DataFrame:
    """Return rows relabelled into explicit calendar-year buckets."""

    year_expr = pl.col(CANONICAL_DATE).cast(pl.Date).dt.year()
    labels = {year: _legacy_year_label(year) for year in selected_years}
    case = None
    for year, label in labels.items():
        if case is None:
            case = pl.when(year_expr == year).then(pl.lit(label))
        else:
            case = case.when(year_expr == year).then(pl.lit(label))
    if case is None:
        return canonical.head(0)
    return (
        canonical.with_columns(case.otherwise(None).alias(CANONICAL_PERIOD))
        .filter(pl.col(CANONICAL_PERIOD).is_not_null())
        .sort([CANONICAL_PERIOD, CANONICAL_DATE])
    )


def _requested_period_comparison_mode(
    spec: dict[str, Any], recipe: dict[str, Any]
) -> str | None:
    """Return an explicitly requested period-comparison mode, if any."""

    options = recipe.get("options") or {}
    raw_mode = (
        spec.get("period_comparison_mode")
        or options.get("period_comparison_mode")
        or ""
    )
    normalized = str(raw_mode).strip().lower().replace("-", "_")
    aliases = {
        "calendar": "calendar_period",
        "calendar_period": "calendar_period",
        "calendar_year": "calendar_period",
        "calendar_years": "calendar_period",
        "complete_calendar_year": "calendar_period",
        "complete_calendar_years": "calendar_period",
        "rolling": "rolling_period",
        "rolling_period": "rolling_period",
        "rolling_window": "rolling_period",
        "r12m": "rolling_period",
        "year_to_date": "year_to_date",
        "ytd": "year_to_date",
    }
    return aliases.get(normalized)


def _uses_period_comparison_window(
    spec: dict[str, Any],
    selected_periods: Sequence[str],
    *,
    requested_mode: str | None,
) -> bool:
    """Return whether a spec should receive protected date-window buckets."""

    legacy_chart_key = str(spec.get("legacy_chart_key") or "")
    if legacy_chart_key in {"areaChart", "timelineChart"}:
        return False
    if str(spec.get("period_selection_mode") or "") == (
        "cohort_recent_periods_with_before_bucket"
    ):
        return False
    if requested_mode is not None:
        return True
    return (
        len([period for period in selected_periods if period]) > 1
        or bool(spec.get("show_cagr"))
        or bool(spec.get("show_total_cagr"))
        or bool(spec.get("related_metrics_bar"))
    )


def _resolve_auto_period_comparison_mode(
    dates: Sequence[date],
    spec: dict[str, Any],
    recipe: dict[str, Any],
) -> str | None:
    """Return the safe default comparison mode for annual raw-date buckets."""

    requested_mode = _requested_period_comparison_mode(spec, recipe)
    if requested_mode is not None:
        return requested_mode
    options = recipe.get("options") or {}
    if spec.get("period_to_date") or options.get("period_to_date"):
        return "year_to_date"
    if spec.get("rolling_comparison") or options.get("rolling_comparison"):
        return "rolling_period"
    if not dates:
        return None
    latest_year = max(value.year for value in dates)
    extents = _year_extents(dates)
    if not _observed_year_is_complete(extents, latest_year):
        return "year_to_date"
    return None


def _year_to_date_period_window(
    canonical: pl.DataFrame,
    names: dict[str, str],
    dates: Sequence[date],
) -> _PeriodWindowSelection | None:
    """Return a YTD comparison window with explicit IBCS underscore labels."""

    if not dates:
        return None
    comparison_end = max(dates)
    comparison_year = comparison_end.year
    baseline_year = comparison_year - 1
    comparison_dates = [
        value
        for value in dates
        if value.year == comparison_year and value <= comparison_end
    ]
    if not comparison_dates:
        return None
    if _observed_date_grain(dates) == "daily":
        baseline_cutoff = _add_years(comparison_end, -1)
        baseline_dates = [
            value
            for value in dates
            if value.year == baseline_year and value <= baseline_cutoff
        ]
    else:
        baseline_dates = [value for value in dates if value.year == baseline_year][
            : len(comparison_dates)
        ]
    comparison_label = _period_window_label(names["toDateSymbol"], comparison_dates[-1])
    baseline_label = (
        _period_window_label(names["toDateSymbol"], baseline_dates[-1])
        if baseline_dates
        else None
    )
    frame = _period_window_frame_for_dates(
        canonical,
        baseline_label=baseline_label,
        baseline_dates=baseline_dates,
        comparison_label=comparison_label,
        comparison_dates=comparison_dates,
    )
    selected_periods = (
        [baseline_label, comparison_label] if baseline_label else [comparison_label]
    )
    selected_periods = [period for period in selected_periods if period]
    return _PeriodWindowSelection(
        frame=frame,
        selected_periods=selected_periods,
        audit={
            "status": "applied",
            "period_comparison_mode": "year_to_date",
            "title_period_context": f"YTD through {comparison_end.isoformat()}",
            "comparison": {
                "label": comparison_label,
                "start_date": comparison_dates[0].isoformat(),
                "end_date": comparison_dates[-1].isoformat(),
                "date_count": len(comparison_dates),
            },
            "baseline": (
                {
                    "label": baseline_label,
                    "start_date": baseline_dates[0].isoformat(),
                    "end_date": baseline_dates[-1].isoformat(),
                    "date_count": len(baseline_dates),
                }
                if baseline_label and baseline_dates
                else None
            ),
            "row_counts": _period_counts(frame),
        },
    )


def _calendar_period_window(
    canonical: pl.DataFrame, dates: Sequence[date]
) -> _PeriodWindowSelection | None:
    """Return a calendar-year window that excludes a partial latest year."""

    if not dates:
        return None
    extents = _year_extents(dates)
    years = sorted(extents)
    latest_year = years[-1]
    complete_years = [
        year for year in years if _observed_year_is_complete(extents, year)
    ]
    if len(complete_years) >= 2:
        selected_years = complete_years[-2:]
        complete_years_only = True
    else:
        candidates = (
            years[:-1]
            if not _observed_year_is_complete(extents, latest_year)
            else years
        )
        selected_years = candidates[-2:] if len(candidates) >= 2 else candidates[-1:]
        complete_years_only = False
    if not selected_years:
        return None
    frame = _period_window_frame_for_years(canonical, selected_years)
    selected_periods = [_legacy_year_label(year) for year in selected_years]
    return _PeriodWindowSelection(
        frame=frame,
        selected_periods=selected_periods,
        audit={
            "status": "applied",
            "period_comparison_mode": "calendar_period",
            "title_period_context": "calendar year",
            "complete_years_only": complete_years_only,
            "complete_years": complete_years,
            "selected_years": selected_years,
            "latest_year": latest_year,
            "latest_year_complete": _observed_year_is_complete(extents, latest_year),
            "row_counts": _period_counts(frame),
        },
    )


def _rolling_period_window(
    canonical: pl.DataFrame,
    names: dict[str, str],
    dates: Sequence[date],
    recipe: dict[str, Any],
) -> _PeriodWindowSelection | None:
    """Return an equal rolling-period comparison with explicit labels."""

    if not dates:
        return None
    options = recipe.get("options") or {}
    try:
        window_months = int(options.get("rolling_window_months") or 12)
    except (TypeError, ValueError):
        window_months = 12
    window_months = max(1, window_months)
    rolling_comparison = (
        str(options.get("rolling_comparison") or "prior_year").strip().lower()
    )
    comparison_end = max(dates)
    comparison_start = _add_months(comparison_end, -(window_months - 1)).replace(day=1)
    if rolling_comparison == "previous_window":
        baseline_start = _add_months(comparison_start, -window_months)
        baseline_end = comparison_start - timedelta(days=1)
    else:
        rolling_comparison = "prior_year"
        baseline_start = _add_months(comparison_start, -12)
        baseline_end = _add_months(comparison_end, -12)
    comparison_label = _period_window_label(
        names["rollingPeriodSymbol"], comparison_end
    )
    baseline_label = _period_window_label(names["rollingPeriodSymbol"], baseline_end)
    frame = _period_window_frame_for_ranges(
        canonical,
        baseline_label=baseline_label,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        comparison_label=comparison_label,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
    )
    selected_periods = [baseline_label, comparison_label]
    return _PeriodWindowSelection(
        frame=frame,
        selected_periods=selected_periods,
        audit={
            "status": "applied",
            "period_comparison_mode": "rolling_period",
            "title_period_context": (
                f"rolling {window_months} months ending {comparison_end.isoformat()}"
            ),
            "rolling_window_months": window_months,
            "rolling_comparison": rolling_comparison,
            "comparison": {
                "label": comparison_label,
                "start_date": comparison_start.isoformat(),
                "end_date": comparison_end.isoformat(),
            },
            "baseline": {
                "label": baseline_label,
                "start_date": baseline_start.isoformat(),
                "end_date": baseline_end.isoformat(),
            },
            "row_counts": _period_counts(frame),
        },
    )


def _safe_year_period_window_selection(
    canonical: pl.DataFrame,
    names: dict[str, str],
    chart: dict[str, Any],
    spec: dict[str, Any],
    recipe: dict[str, Any],
    selected_periods: list[str],
) -> _PeriodWindowSelection | None:
    """Return safe annual date-window buckets for comparison charts.

    Date-window selection is deterministic here because the boundaries and
    labels are mechanically verifiable from the mapped source date column.
    """

    dates = _unique_canonical_dates(canonical)
    requested_mode = _requested_period_comparison_mode(spec, recipe)
    if not _uses_period_comparison_window(
        spec,
        selected_periods,
        requested_mode=requested_mode,
    ):
        return None
    mode = _resolve_auto_period_comparison_mode(dates, spec, recipe)
    if mode == "year_to_date":
        selection = _year_to_date_period_window(canonical, names, dates)
        if selection is not None:
            chart[names["periodToDate"]] = True
            chart[names["compareWithYearBefore"]] = False
        return selection
    if mode == "rolling_period":
        selection = _rolling_period_window(canonical, names, dates, recipe)
        if selection is not None:
            chart[names["periodToDate"]] = False
            chart[names["compareWithYearBefore"]] = True
        return selection
    if mode == "calendar_period":
        selection = _calendar_period_window(canonical, dates)
        if selection is not None:
            chart[names["periodToDate"]] = False
            chart[names["compareWithYearBefore"]] = False
        return selection
    return None


def _apply_period_window_to_chart(
    names: dict[str, str],
    chart: dict[str, Any],
    selection: _PeriodWindowSelection,
) -> None:
    """Write resolved period-window labels back to the legacy chart dict."""

    chart[names["selectedPeriods"]] = selection.selected_periods
    chart[names["toPlotPeriod"]] = selection.selected_periods[-1]
    chart[names["periodChoice"]] = names["yearName"]
    chart[names["datePeriodName"]] = names["yearName"]


def _apply_legacy_period_grain_selection(
    canonical: pl.DataFrame,
    names: dict[str, str],
    chart: dict[str, Any],
    spec: dict[str, Any],
    recipe: dict[str, Any],
    selected_periods: list[str],
) -> tuple[pl.DataFrame, list[str], dict[str, Any], dict[str, Any]]:
    """Apply legacy period aggregation and period selection for raw date periods."""

    period_grain = str(spec.get("period_grain") or "").strip().lower()
    period_values = _period_values_from_frame(canonical, CANONICAL_PERIOD)
    period_selection = str(
        (recipe.get("options") or {}).get("period_selection") or ""
    ).strip()
    if (
        not period_grain
        and period_selection in {"", "infer_current_or_all"}
        and _period_labels_look_like_raw_dates(period_values)
    ):
        period_grain = "year"
        chart[names["periodChoice"]] = names["yearName"]
        chart[names["datePeriodName"]] = names["yearName"]
    if period_grain == "year" and CANONICAL_DATE in canonical.columns:
        safe_selection = _safe_year_period_window_selection(
            canonical,
            names,
            chart,
            spec,
            recipe,
            selected_periods,
        )
        if safe_selection is not None:
            _apply_period_window_to_chart(names, chart, safe_selection)
            return (
                safe_selection.frame,
                safe_selection.selected_periods,
                chart,
                {
                    **safe_selection.audit,
                    "period_grain": period_grain,
                    "input_periods": period_values,
                    "selected_periods": safe_selection.selected_periods,
                },
            )
    if (
        period_grain not in {"year", "quarter", "month", "week"}
        or CANONICAL_DATE not in canonical.columns
        or not _period_labels_look_like_raw_dates(period_values)
    ):
        return (
            _frame_for_spec_period_grain(canonical, spec),
            selected_periods,
            chart,
            {"status": "skipped", "reason": "not_raw_date_period_grain"},
        )

    try:
        from modules.data.identify_columns import (  # noqa: PLC0415
            convert_date_to_period,
            filter_out_useless_periods,
        )
    except ModuleNotFoundError as exc:
        return (
            _frame_for_spec_period_grain(canonical, spec),
            selected_periods,
            chart,
            {"status": "skipped", "reason": f"legacy_period_import_failed:{exc}"},
        )

    if period_grain == "year":
        safe_selection = _safe_year_period_window_selection(
            canonical,
            names,
            chart,
            spec,
            recipe,
            selected_periods,
        )
        if safe_selection is not None:
            _apply_period_window_to_chart(names, chart, safe_selection)
            return (
                safe_selection.frame,
                safe_selection.selected_periods,
                chart,
                {
                    **safe_selection.audit,
                    "period_grain": period_grain,
                    "input_periods": period_values,
                    "selected_periods": safe_selection.selected_periods,
                },
            )

    param = _legacy_param_dict(
        names,
        total=0.0,
        selected_periods=selected_periods,
        period_totals={},
        columns=canonical.columns,
        date_period_choice=chart.get(names["datePeriodName"]),
    )
    _put_if_key(param, names, "dateColFound", True)
    _put_if_key(param, names, "periodColFound", False)
    _put_if_key(param, names, "impossibleToProcessFile", False)

    try:
        periodized, param = convert_date_to_period(canonical.lazy(), param, chart)
        filtered, _period_frame, _all_periods, param, chart = (
            filter_out_useless_periods(periodized, param, chart)
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        pl.exceptions.PolarsError,
    ) as exc:
        return (
            _frame_for_spec_period_grain(canonical, spec),
            selected_periods,
            chart,
            {"status": "skipped", "reason": f"legacy_period_conversion_failed:{exc}"},
        )

    effective_periods = [
        str(item)
        for item in (
            chart.get(names["selectedPeriods"])
            or param.get(names["selectedPeriods"])
            or []
        )
    ]
    frame = (
        _collect_lazyframe(filtered) if isinstance(filtered, pl.LazyFrame) else filtered
    )
    if frame.is_empty():
        frame = (
            _collect_lazyframe(periodized)
            if isinstance(periodized, pl.LazyFrame)
            else periodized
        )
    if not effective_periods:
        effective_periods = _period_values_from_frame(frame, CANONICAL_PERIOD)
    if period_grain in {"quarter", "month", "week"} and period_selection in {
        "",
        "infer_current_or_all",
    }:
        target_period_count = len(effective_periods or selected_periods)
        if (
            _requested_period_comparison_mode(spec, recipe) is None
            and len(selected_periods) == 1
        ):
            target_period_count = 1
        dated_periods = _latest_period_values_by_date(
            frame,
            CANONICAL_PERIOD,
            CANONICAL_DATE,
            target_period_count,
        )
        if dated_periods:
            effective_periods = dated_periods
    if effective_periods:
        chart[names["selectedPeriods"]] = effective_periods
        chart[names["toPlotPeriod"]] = effective_periods[-1]
    return (
        frame,
        effective_periods or selected_periods,
        chart,
        {
            "status": "applied",
            "period_grain": period_grain,
            "input_periods": period_values,
            "selected_periods": effective_periods or selected_periods,
        },
    )


def _apply_cohort_period_bucket(
    frame: pl.DataFrame,
    spec: dict[str, Any],
) -> pl.DataFrame:
    """Aggregate older cohort periods into the configured before bucket."""

    before_label = spec.get("cohort_before_period_label")
    visible_periods = [
        str(period) for period in spec.get("cohort_visible_periods") or []
    ]
    if not before_label or not visible_periods or CANONICAL_PERIOD not in frame.columns:
        return frame
    return frame.with_columns(
        pl.when(pl.col(CANONICAL_PERIOD).cast(pl.Utf8).is_in(visible_periods))
        .then(pl.col(CANONICAL_PERIOD).cast(pl.Utf8))
        .otherwise(pl.lit(str(before_label)))
        .alias(CANONICAL_PERIOD)
    )


def _legacy_df_dict(
    names: dict[str, str], frame: pl.DataFrame
) -> dict[str, pl.DataFrame]:
    return {
        names["dfDatesName"]: frame,
        names["dfPeriodsName"]: frame,
        names["dfAllPeriodsName"]: frame,
        names["dfSnapshotName"]: frame,
        names["dfName"]: frame,
    }


def _legacy_index_dimensions(recipe: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Return recipe and spec dimensions that legacy charting may group by."""

    dimensions: list[str] = []
    spec_dimensions = list(spec.get("dimensions") or [])
    recipe_dimensions = list(recipe["mappings"].get("dimensions") or [])
    if (
        spec.get("dimension_selection")
        == "panel_dimension_item_dimension_multitier_bar"
    ):
        leading_dimensions = spec_dimensions
        trailing_dimensions = recipe_dimensions
    else:
        leading_dimensions = recipe_dimensions
        trailing_dimensions = spec_dimensions
    candidates = [
        *leading_dimensions,
        *trailing_dimensions,
        spec.get("x_dimension"),
        spec.get("y_dimension"),
        spec.get("cohort_dimension"),
        spec.get("cohort_source_dimension"),
    ]
    for item in candidates:
        if item is None:
            continue
        dimension = str(item)
        if dimension and dimension not in dimensions:
            dimensions.append(dimension)
    return dimensions


def _legacy_source_functions(spec: dict[str, Any]) -> list[str]:
    plotter = str(spec["plotter"])
    draw_functions = {
        "plot_mekko_charts": [
            "modules.charting.prepare_charts.group_by_dataset_for_marimekko_and_barmekko",
            "modules.charting.draw_width_and_stacked_plots.draw_mekko_chart",
        ],
        "plot_stacked_bar_charts": [
            "modules.charting.prepare_charts.group_by_dataset_for_stacked_bar",
            "modules.data.multidimensional_charts_prep.prepare_data_for_stacked_bar_one_dimension",
            "modules.data.multidimensional_charts_prep.prepare_data_for_stacked_bar_two_dimensions",
            "modules.charting.draw_width_and_stacked_plots.draw_stacked_bar_chart",
        ],
        "plot_stacked_column_charts": [
            "modules.data.multidimensional_charts_prep.prepare_data_for_stacked_column",
            "modules.charting.draw_width_and_stacked_plots.draw_stacked_column_chart",
        ],
        "plot_area_charts": [
            "modules.charting.prepare_charts.resample_dates",
            "modules.charting.draw_other_charts.draw_area_chart",
        ],
        "plot_timeline_charts": [
            "modules.charting.prepare_charts.resample_dates",
            "modules.data.time_series_data_prep.prepare_data_for_timeline_plot",
            "modules.charting.draw_timeline.draw_timeline_chart",
            "modules.charting.draw_timeline.add_annotations_to_timeline",
            "modules.charting.draw_timeline.add_labels_to_timeline_chart",
        ],
        "plot_horizontal_waterfall_chart": [
            "modules.charting.prepare_charts.resample_dates",
            "modules.data.waterfall_data_prep.prepare_data_for_horizontal_waterfall_plot",
            "modules.data.waterfall_data_prep.prepare_data_for_waterfall",
            "modules.charting.draw_waterfall.draw_horizontal_waterfall_chart",
            "modules.charting.draw_waterfall.add_annotations_to_horizontal_waterfall_plot",
            "modules.charting.draw_waterfall.adjust_horizontal_waterfall_plot",
        ],
        "plot_pareto_chart": [
            "modules.data.misc_charts_data_prep.prepare_data_for_pareto",
            "modules.charting.draw_pareto.draw_pareto_chart",
        ],
        "plot_stacked_pareto_chart": [
            "modules.data.misc_charts_data_prep.prepare_data_for_pareto",
            "modules.charting.draw_width_and_stacked_plots.stacked_bar_width_plot",
        ],
        "plot_multitier_bar_chart": [
            "modules.charting.draw_multitier.draw_multitier_bar_chart",
        ],
        "plot_multitier_column_chart": [
            "modules.charting.prepare_charts.resample_dates",
            "modules.charting.draw_multitier.draw_multitier_column_chart",
        ],
    }
    functions = [
        "modules.charting.run_charting.run_charting",
        f"modules.charting.plot_charts.{plotter}",
        *draw_functions.get(plotter, []),
    ]
    if spec.get("synthesis_plot"):
        functions.extend(
            [
                "modules.data.multidimensional_charts_prep.prepare_data_for_syn_plot",
                "modules.charting.plotting_utilities.make_syn_plot_comment_dataset",
                "modules.charting.plotting_utilities.aggregate_syn_plot_data",
                "modules.charting.setup_fig.add_by_to_syn_plot_col_labels",
                "modules.charting.draw_width_and_stacked_plots.stacked_bar_width_plot",
                "modules.charting.draw_width_and_stacked_plots.adjust_stacked_column_plot",
            ]
        )
    is_stacked_bar_small_multiple = (
        spec.get("small_multiples_dimension")
        and spec.get("plotter") == "plot_stacked_bar_charts"
    )
    if is_stacked_bar_small_multiple:
        functions.extend(
            [
                "modules.charting.draw_width_and_stacked_plots.draw_stacked_bar_small_multiples",
                "modules.data.multidimensional_charts_prep.prepare_small_multiples_dataframe_for_stacked_bar",
            ]
        )
    if spec.get("related_metrics_bar"):
        functions.extend(
            [
                "modules.data.multidimensional_charts_prep.prepare_overlay_data_for_stacked_bar",
                "modules.charting.draw_charts_utils.add_overlay_trace",
            ]
        )
    return functions


def _collect_lazyframe(frame: pl.LazyFrame) -> pl.DataFrame:
    try:
        return frame.collect(engine="streaming")
    except (TypeError, ValueError, RuntimeError, pl.exceptions.PolarsError):
        return frame.collect()


def _json_safe(value: Any) -> Any:
    if isinstance(value, pl.LazyFrame):
        return {"type": "LazyFrame", "columns": value.collect_schema().names()}
    if isinstance(value, pl.DataFrame):
        return {
            "type": "DataFrame",
            "columns": value.columns,
            "row_count": value.height,
        }
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, TypeError, ValueError):
            return str(value)
    return value


def _frame_payload(frame: Any) -> dict[str, Any]:
    if isinstance(frame, pl.LazyFrame):
        collected = _collect_lazyframe(frame)
    elif isinstance(frame, pl.DataFrame):
        collected = frame
    else:
        return {
            "type": type(frame).__name__,
            "columns": [],
            "row_count": None,
            "rows": [],
            "repr": str(frame)[:1000],
        }
    return {
        "type": type(frame).__name__,
        "columns": collected.columns,
        "row_count": collected.height,
        "rows": _json_safe(collected.to_dicts()),
    }


def _figure_payload(fig: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": type(fig).__name__, "traces": []}
    layout = getattr(fig, "layout", None)
    payload["layout_width"] = _json_safe(getattr(layout, "width", None))
    payload["layout_height"] = _json_safe(getattr(layout, "height", None))
    title = getattr(layout, "title", None) if layout is not None else None
    payload["title"] = str(getattr(title, "text", "") or "")
    annotations = _sequence(getattr(layout, "annotations", None)) if layout else []
    payload["annotations"] = [
        {
            "text": str(getattr(annotation, "text", "") or ""),
            "x": _json_safe(getattr(annotation, "x", None)),
            "y": _json_safe(getattr(annotation, "y", None)),
        }
        for annotation in annotations
    ]
    for trace in _sequence(getattr(fig, "data", None)):
        marker = getattr(trace, "marker", None)
        payload["traces"].append(
            {
                "type": str(getattr(trace, "type", "") or ""),
                "name": str(getattr(trace, "name", "") or ""),
                "x": _json_safe(_sequence(getattr(trace, "x", None))),
                "y": _json_safe(_sequence(getattr(trace, "y", None))),
                "width": _json_safe(_sequence(getattr(trace, "width", None))),
                "text": _json_safe(_sequence(getattr(trace, "text", None))),
                "marker_color": _json_safe(
                    getattr(marker, "color", None) if marker is not None else None
                ),
            }
        )
    return payload


def _sequence(value: Any) -> list[Any]:
    """Return Plotly array-like values as a plain list."""

    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return [value]


def _numeric_trace_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        values: list[float] = []
        for item in value:
            values.extend(_numeric_trace_values(item))
        return values
    return []


def _context_trace_widths(figures: list[Any], spec: dict[str, Any]) -> list[float]:
    widths: list[float] = []
    for fig in figures:
        for trace in _sequence(getattr(fig, "data", None)):
            widths.extend(
                _numeric_trace_values(_sequence(getattr(trace, "width", None)))
            )
    if not widths and spec.get("synthesis_plot"):
        for fig in figures:
            layout = getattr(fig, "layout", None)
            bargap = getattr(layout, "bargap", None) if layout is not None else None
            if isinstance(bargap, (int, float)) and not isinstance(bargap, bool):
                widths.append(max(0.0, 1.0 - float(bargap)))
    return sorted({round(width, 4) for width in widths})


def _float_or_none(value: Any) -> float | None:
    """Return a float when the Plotly/captured value is numeric."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _axis_name(trace: Any, axis: str) -> str:
    """Return a stable Plotly axis id for grouping subplot traces."""

    raw = getattr(trace, f"{axis}axis", None)
    return str(raw or axis)


def _related_metric_panel_titles(fig: Any) -> list[str]:
    """Return visible subplot titles from a Plotly figure when available."""

    layout = getattr(fig, "layout", None)
    annotations = _sequence(getattr(layout, "annotations", None)) if layout else []
    titles: list[str] = []
    for annotation in annotations:
        text = str(getattr(annotation, "text", "") or "").strip()
        if not text or text.lower().startswith("total"):
            continue
        if "<br" in text.lower() or "bar chart:" in text.lower():
            continue
        if _looks_like_related_metric_value_label(text):
            continue
        if text not in titles:
            titles.append(text)
    return titles


def _looks_like_related_metric_value_label(text: str) -> bool:
    """Return whether annotation text is a value label, not a panel title."""

    normalized = text.strip().replace(",", "")
    return bool(
        re.fullmatch(
            r"[+-]?\d+(?:\.\d+)?(?:%|\s*\(\d+(?:\.\d+)?%\))?",
            normalized,
        )
    )


def _related_metric_rows_from_figures(
    figures: list[Any],
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return model-readable rows for legacy bar-with-marker charts."""

    metrics = [str(item) for item in spec.get("metrics") or []]
    primary_metric = metrics[0] if metrics else str(spec.get("metric") or "")
    marker_metric = metrics[1] if len(metrics) > 1 else ""
    rows: list[dict[str, Any]] = []
    for figure_index, fig in enumerate(figures, start=1):
        panel_titles = _related_metric_panel_titles(fig)
        bars_by_axis: dict[str, list[Any]] = {}
        markers_by_axis: dict[str, list[Any]] = {}
        for trace in _sequence(getattr(fig, "data", None)):
            trace_type = str(getattr(trace, "type", "") or "")
            mode = str(getattr(trace, "mode", "") or "")
            axis = _axis_name(trace, "y")
            if trace_type == "bar":
                bars_by_axis.setdefault(axis, []).append(trace)
            elif trace_type == "scatter" and "markers" in mode:
                markers_by_axis.setdefault(axis, []).append(trace)
        for panel_index, axis in enumerate(sorted(bars_by_axis), start=1):
            bar_trace = max(
                bars_by_axis[axis],
                key=lambda trace: len(_sequence(getattr(trace, "y", None))),
            )
            raw_categories = _sequence(getattr(bar_trace, "y", None))
            raw_primary_values = [
                _float_or_none(item)
                for item in _sequence(getattr(bar_trace, "x", None))
            ]
            primary_labels = _sequence(getattr(bar_trace, "text", None))
            category_indexes = [
                index
                for index, category in enumerate(raw_categories)
                if category is not None and str(category) != "None"
            ]
            categories = [str(raw_categories[index]) for index in category_indexes]
            primary_values = [
                (raw_primary_values[index] if index < len(raw_primary_values) else None)
                for index in category_indexes
            ]
            primary_labels = [
                primary_labels[index] if index < len(primary_labels) else None
                for index in category_indexes
            ]
            marker_values: list[float | None] = [None] * len(raw_categories)
            marker_labels: list[Any] = [None] * len(raw_categories)
            marker_trace = (markers_by_axis.get(axis) or [None])[0]
            if marker_trace is not None:
                raw_marker_values = _sequence(getattr(marker_trace, "x", None))
                raw_marker_labels = _sequence(getattr(marker_trace, "text", None))
                marker_y = _sequence(getattr(marker_trace, "y", None))
                if len(raw_marker_values) == len(raw_categories):
                    marker_values = [_float_or_none(item) for item in raw_marker_values]
                    marker_labels = [
                        (
                            raw_marker_labels[index]
                            if index < len(raw_marker_labels)
                            else None
                        )
                        for index in range(len(raw_categories))
                    ]
                else:
                    position_map: dict[int, int] = {}
                    for marker_index, y_value in enumerate(marker_y):
                        numeric_y = _float_or_none(y_value)
                        if numeric_y is not None:
                            position_map[int(numeric_y)] = marker_index
                    for category_index in range(len(raw_categories)):
                        marker_index = position_map.get(category_index)
                        if marker_index is None:
                            continue
                        marker_values[category_index] = _float_or_none(
                            raw_marker_values[marker_index]
                            if marker_index < len(raw_marker_values)
                            else None
                        )
                        marker_labels[category_index] = (
                            raw_marker_labels[marker_index]
                            if marker_index < len(raw_marker_labels)
                            else None
                        )
            total = sum(abs(value or 0.0) for value in primary_values)
            panel_label = (
                panel_titles[panel_index - 1]
                if panel_index - 1 < len(panel_titles)
                else ("Total" if not spec.get("small_multiples_dimension") else axis)
            )
            panel_rows: list[dict[str, Any]] = []
            for index, category in enumerate(categories):
                source_index = category_indexes[index]
                primary_value = (
                    primary_values[index] if index < len(primary_values) else None
                )
                marker_value = (
                    marker_values[source_index]
                    if source_index < len(marker_values)
                    else None
                )
                share = (
                    abs(primary_value) / total
                    if primary_value is not None and total > 0
                    else None
                )
                panel_rows.append(
                    {
                        "figure_index": figure_index,
                        "panel": panel_label,
                        "axis": axis,
                        "item": category,
                        "primary_metric": primary_metric,
                        "primary_value": primary_value,
                        "primary_label": (
                            primary_labels[index]
                            if index < len(primary_labels)
                            else None
                        ),
                        "share_of_panel_total": share,
                        "marker_metric": marker_metric,
                        "marker_value": marker_value,
                        "marker_label": (
                            marker_labels[source_index]
                            if source_index < len(marker_labels)
                            else None
                        ),
                        "is_other_bucket": "other rank" in category.lower(),
                    }
                )
            ranked = sorted(
                panel_rows,
                key=lambda row: (
                    bool(row["is_other_bucket"]),
                    -abs(float(row["primary_value"] or 0.0)),
                ),
            )
            rank_by_item = {
                str(row["item"]): rank for rank, row in enumerate(ranked, 1)
            }
            for row in panel_rows:
                row["rank_by_primary_metric"] = rank_by_item.get(str(row["item"]))
            rows.extend(panel_rows)
    notable: list[dict[str, Any]] = []
    for row in rows:
        share = row.get("share_of_panel_total")
        marker_value = row.get("marker_value")
        if not isinstance(share, float) or marker_value is None:
            continue
        if share >= 0.10 and float(marker_value) < 0:
            pattern = "large_declining_item"
        elif share >= 0.10 and float(marker_value) > 0:
            pattern = "large_growing_item"
        elif share < 0.05 and float(marker_value) >= 20:
            pattern = "small_fast_growing_item"
        else:
            continue
        notable.append(
            {
                "pattern": pattern,
                "panel": row["panel"],
                "item": row["item"],
                "primary_metric": row["primary_metric"],
                "primary_value": row["primary_value"],
                "share_of_panel_total": share,
                "marker_metric": row["marker_metric"],
                "marker_value": marker_value,
            }
        )
    return rows, notable


def _legacy_chart_label_audit(
    names: dict[str, str], chart: dict[str, Any]
) -> dict[str, Any]:
    """Return legacy label settings that affect visible chart text."""

    return {
        "show_values_as": chart.get(names["showValuesAs"]),
        "show_legend": chart.get(names["showLegend"]),
    }


def _strip_legacy_by_prefix(value: Any) -> str:
    text = str(value or "")
    return text[3:] if text.startswith("by ") else text


def _axis_tick_labels(fig: Any) -> dict[float, str]:
    layout = getattr(fig, "layout", None)
    axis = getattr(layout, "xaxis", None) if layout is not None else None
    tickvals = _sequence(getattr(axis, "tickvals", None))
    ticktext = _sequence(getattr(axis, "ticktext", None))
    labels: dict[float, str] = {}
    for tick_value, label in zip(tickvals, ticktext):
        try:
            numeric_tick = float(tick_value)
        except (TypeError, ValueError):
            continue
        text = str(label)
        labels[numeric_tick] = text
        labels[numeric_tick - 0.5] = text
    return labels


def _series_rows_by_dimension(
    figures: list[Any], dimensions: list[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for figure_index, fig in enumerate(figures, start=1):
        tick_labels = _axis_tick_labels(fig)
        for trace in _sequence(getattr(fig, "data", None)):
            x_values = _sequence(getattr(trace, "x", None))
            y_values = _sequence(getattr(trace, "y", None))
            text_values = _sequence(getattr(trace, "text", None))
            item = _strip_legacy_by_prefix(getattr(trace, "name", ""))
            for point_index, (x_value, y_value) in enumerate(zip(x_values, y_values)):
                if y_value is None:
                    continue
                try:
                    position = int(x_value)
                except (TypeError, ValueError):
                    continue
                axis_label = tick_labels.get(float(position))
                dimension = (
                    axis_label
                    if axis_label is not None
                    else (
                        dimensions[position]
                        if 0 <= position < len(dimensions)
                        else str(x_value)
                    )
                )
                rows.append(
                    {
                        "figure_index": figure_index,
                        "position": position,
                        "dimension": dimension,
                        "source_dimension": dimensions[0] if dimensions else None,
                        "axis_label": axis_label,
                        "item": item,
                        "value": _json_safe(y_value),
                        "text": _json_safe(
                            text_values[point_index]
                            if point_index < len(text_values)
                            else None
                        ),
                    }
                )
    return rows


def _waterfall_panel_titles(fig: Any) -> list[str]:
    layout = getattr(fig, "layout", None)
    annotations = _sequence(getattr(layout, "annotations", None)) if layout else []
    panel_titles: list[tuple[float, float, str]] = []
    for annotation in annotations:
        text = str(getattr(annotation, "text", "") or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if "<br" in lowered or lowered.startswith("date="):
            continue
        x_value = _float_or_none(getattr(annotation, "x", None)) or 0.0
        y_value = _float_or_none(getattr(annotation, "y", None)) or 0.0
        panel_titles.append((y_value, x_value, text))
    return [
        text
        for _y_value, _x_value, text in sorted(
            panel_titles,
            key=lambda row: (-row[0], row[1]),
        )
    ]


def _waterfall_rows_from_figures(figures: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for figure_index, fig in enumerate(figures, start=1):
        panel_titles = _waterfall_panel_titles(fig)
        panel_index = -1
        for trace in _sequence(getattr(fig, "data", None)):
            trace_type = str(getattr(trace, "type", "") or "")
            if trace_type == "waterfall":
                panel_index += 1
            if trace_type not in {"waterfall", "bar"}:
                continue
            panel = (
                panel_titles[panel_index]
                if 0 <= panel_index < len(panel_titles)
                else None
            )
            x_values = _sequence(getattr(trace, "x", None))
            y_values = _sequence(getattr(trace, "y", None))
            text_values = _sequence(getattr(trace, "text", None))
            for point_index, (x_value, y_value) in enumerate(zip(x_values, y_values)):
                rows.append(
                    {
                        "figure_index": figure_index,
                        "panel_index": panel_index + 1 if panel_index >= 0 else None,
                        "panel": panel,
                        "trace_type": trace_type,
                        "trace_name": str(getattr(trace, "name", "") or ""),
                        "step": _json_safe(x_value),
                        "value": _json_safe(y_value),
                        "text": _json_safe(
                            text_values[point_index]
                            if point_index < len(text_values)
                            else None
                        ),
                    }
                )
    return rows


def _trace_dimension_position(trace: Any) -> int | None:
    x_values = _sequence(getattr(trace, "x", None))
    y_values = _sequence(getattr(trace, "y", None))
    for x_value, y_value in zip(x_values, y_values):
        if y_value is None:
            continue
        try:
            return int(x_value)
        except (TypeError, ValueError):
            return None
    return None


def _trace_active_value(trace: Any) -> float:
    y_values = _sequence(getattr(trace, "y", None))
    for y_value in y_values:
        if y_value is None:
            continue
        try:
            return float(y_value)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _trace_color(trace: Any) -> Any:
    marker = getattr(trace, "marker", None)
    return getattr(marker, "color", None) if marker is not None else None


def _set_trace_color(trace: Any, color: Any) -> None:
    marker = getattr(trace, "marker", None)
    if marker is not None:
        marker.color = color


def _format_synthesis_share(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(numeric) < 0.05:
        return ""
    if abs(numeric - round(numeric)) < 0.05:
        return f"{numeric:.0f}%"
    return f"{numeric:.1f}%"


def _has_synthesis_total_percent_label(fig: Any, x_value: float) -> bool:
    """Return whether a synthesis total label already exists at ``x_value``."""

    layout = getattr(fig, "layout", None)
    if layout is None:
        return False
    for annotation in _sequence(getattr(layout, "annotations", None)):
        text = str(getattr(annotation, "text", "") or "").strip()
        if text != SYNTHESIS_TOTAL_PERCENT_LABEL:
            continue
        if str(getattr(annotation, "xref", "") or "") != "x":
            continue
        if str(getattr(annotation, "yref", "") or "") != "paper":
            continue
        annotation_x = _float_or_none(getattr(annotation, "x", None))
        if annotation_x is not None and abs(annotation_x - x_value) <= 0.01:
            return True
    return False


def _add_synthesis_total_percent_labels(fig: Any, tick_values: list[float]) -> None:
    """Add 100% labels above normalized synthesis columns."""

    for tick_value in tick_values:
        if _has_synthesis_total_percent_label(fig, tick_value):
            continue
        annotation = {
            "text": SYNTHESIS_TOTAL_PERCENT_LABEL,
            "x": tick_value,
            "y": 1.0,
            "xref": "x",
            "yref": "paper",
            "showarrow": False,
            "xanchor": "center",
            "yanchor": "bottom",
            "yshift": -14,
            "font": {"color": "#2F3437", "size": 12},
        }
        if hasattr(fig, "add_annotation"):
            fig.add_annotation(**annotation)
            continue
        layout = getattr(fig, "layout", None)
        if layout is None:
            continue
        annotations = _sequence(getattr(layout, "annotations", None))
        annotations.append(SimpleNamespace(**annotation))
        layout.annotations = annotations


def _apply_uniform_synthesis_palette(figures: list[Any]) -> None:
    """Reset synthesis colors by rank inside each column."""

    for fig in figures:
        traces = _sequence(getattr(fig, "data", None))
        base_colors = [
            _trace_color(trace) for trace in traces if _trace_color(trace) is not None
        ]
        if not base_colors:
            continue
        by_position: dict[int, list[tuple[int, Any]]] = {}
        for index, trace in enumerate(traces):
            position = _trace_dimension_position(trace)
            if position is None:
                continue
            by_position.setdefault(position, []).append((index, trace))
        for position_traces in by_position.values():
            ranked = sorted(
                position_traces,
                key=lambda pair: (
                    "others rank"
                    in _strip_legacy_by_prefix(getattr(pair[1], "name", "")).lower(),
                    -abs(_trace_active_value(pair[1])),
                    pair[0],
                ),
            )
            for rank, (_index, trace) in enumerate(ranked):
                item = _strip_legacy_by_prefix(getattr(trace, "name", "")).lower()
                color = (
                    "#d9d9d9"
                    if "others rank" in item
                    else base_colors[rank % len(base_colors)]
                )
                _set_trace_color(trace, color)


def _apply_related_metric_marker_color(figures: list[Any]) -> None:
    """Use one marker color for related-metric bar overlays."""

    for fig in figures:
        for trace in _sequence(getattr(fig, "data", None)):
            trace_type = str(getattr(trace, "type", "") or "")
            mode = str(getattr(trace, "mode", "") or "")
            if trace_type != "scatter" or "markers" not in mode:
                continue
            marker = getattr(trace, "marker", None)
            if marker is None:
                continue
            marker.color = RELATED_METRIC_MARKER_COLOR
            marker.size = RELATED_METRIC_MARKER_SIZE
            marker_line = getattr(marker, "line", None)
            if marker_line is not None:
                marker_line.color = RELATED_METRIC_MARKER_COLOR


def _period_window_title_suffix(period_adapter_audit: dict[str, Any]) -> str | None:
    """Return visible period-window context for chart titles."""

    mode = period_adapter_audit.get("period_comparison_mode")
    if mode == "year_to_date":
        return period_adapter_audit.get("title_period_context") or "YTD"
    if mode == "rolling_period":
        return period_adapter_audit.get("title_period_context") or "rolling period"
    if mode == "calendar_period":
        return period_adapter_audit.get("title_period_context") or "calendar year"
    return None


def _append_period_window_suffix(text: Any, suffix: str) -> str:
    """Append period-window context to a title if it is not already present."""

    title = str(text or "")
    if not title or suffix in title:
        return title
    lower_title = title.lower()
    lower_suffix = suffix.lower()
    if lower_suffix in lower_title:
        return title
    separator = ", " if " vs " in title else "<br>"
    return f"{title}{separator}{suffix}"


def _replace_period_window_generic_comparison(
    text: Any, period_adapter_audit: dict[str, Any]
) -> str:
    """Replace generic AC/PY wording with resolved period-window labels."""

    title = str(text or "")
    selected_periods = [
        str(period)
        for period in period_adapter_audit.get("selected_periods") or []
        if period
    ]
    if len(selected_periods) < 2:
        return title
    baseline_label = selected_periods[0]
    comparison_label = selected_periods[-1]
    resolved = f"{comparison_label} vs {baseline_label}"
    if resolved in title:
        return title
    replacements = (
        (f"{comparison_label} AC vs PY", resolved),
        (f"{comparison_label} AC vs Previous Year", resolved),
        ("AC vs PY", resolved),
        ("AC vs Previous Year", resolved),
    )
    for before, after in replacements:
        if before in title:
            return title.replace(before, after)
    return title


def _is_period_window_title_annotation(annotation: Any) -> bool:
    """Return whether an annotation is likely the chart title/subtitle."""

    text = str(getattr(annotation, "text", "") or "").strip()
    if not text:
        return False
    normalized = re.sub(r"<[^>]+>", "", text).strip().lower()
    if normalized.startswith("total"):
        return False
    if normalized.startswith("abc by sorted"):
        return True
    return "<b>" in text or " vs " in text


def _apply_period_window_title_context(
    figures: list[Any], period_adapter_audit: dict[str, Any]
) -> None:
    """Show whether annual buckets are YTD, calendar, or rolling windows."""

    suffix = _period_window_title_suffix(period_adapter_audit)
    if not suffix:
        return
    for fig in figures:
        layout = getattr(fig, "layout", None)
        title = getattr(layout, "title", None) if layout is not None else None
        title_text = str(getattr(title, "text", "") or "")
        if title_text:
            title.text = _append_period_window_suffix(
                _replace_period_window_generic_comparison(
                    title_text, period_adapter_audit
                ),
                suffix,
            )
            continue
        annotations = list(_sequence(getattr(layout, "annotations", None)))
        for annotation in annotations:
            text = str(getattr(annotation, "text", "") or "")
            if _is_period_window_title_annotation(annotation):
                annotation.text = _append_period_window_suffix(
                    _replace_period_window_generic_comparison(
                        text, period_adapter_audit
                    ),
                    suffix,
                )
                break


def _html_title_lines(text: Any) -> list[str]:
    """Return non-empty HTML title lines split on Plotly line breaks."""

    return plotly_title_lines(text)


def _plain_title_text(text: Any) -> str:
    """Return title text with simple Plotly HTML stripped."""

    return plain_plotly_title_text(text)


def _contract_title_lines(lines: Sequence[Any]) -> list[str]:
    """Return who, what, and when rows from a visible reporting title."""

    cleaned = [_plain_title_text(line) for line in lines if _plain_title_text(line)]
    if len(cleaned) < 3:
        return []
    return [cleaned[0], cleaned[1], cleaned[-1]]


def _title_contract_payload(lines: Sequence[Any]) -> dict[str, Any]:
    """Return context metadata for the standard three-row title contract."""

    contract_lines = _contract_title_lines(lines)
    if len(contract_lines) < 3:
        return {}
    return {
        "chart_title_lines": contract_lines,
        "title_contract": {
            "who": contract_lines[0],
            "what": contract_lines[1],
            "when": contract_lines[2],
        },
    }


def _title_lines_from_figure(fig: Any) -> list[str]:
    """Extract reporting title rows from a Plotly figure or title annotation."""

    layout = getattr(fig, "layout", None)
    if layout is None:
        return []
    title = getattr(layout, "title", None)
    title_text = str(getattr(title, "text", "") or "") if title else ""
    lines = _contract_title_lines(_html_title_lines(title_text))
    if len(lines) >= 3:
        return lines
    for annotation in _sequence(getattr(layout, "annotations", None)):
        if not _is_period_window_title_annotation(annotation):
            continue
        lines = _contract_title_lines(
            _html_title_lines(str(getattr(annotation, "text", "") or ""))
        )
        if len(lines) >= 3:
            return lines
    return []


def _period_line_for_reporting_title(
    lines: list[str],
    spec: dict[str, Any],
    period_adapter_audit: dict[str, Any],
) -> str:
    """Return the single period line for the reporting title."""

    suffix = _period_window_title_suffix(period_adapter_audit)
    mode = period_adapter_audit.get("period_comparison_mode")
    candidate_lines = [line for line in lines[1:] if _plain_title_text(line)]
    if suffix:
        if mode in {"year_to_date", "rolling_period"}:
            return str(suffix)
        if mode == "calendar_period":
            period = _plain_title_text(candidate_lines[0]) if candidate_lines else ""
            return f"{period} {suffix}".strip() if period else str(suffix)
    period_window_line = _period_line_from_spec_period_window(spec)
    if period_window_line:
        return period_window_line
    if candidate_lines:
        return _plain_title_text(candidate_lines[-1])
    selected_periods = [
        str(period) for period in spec.get("selected_periods") or [] if period
    ]
    return selected_periods[-1] if selected_periods else ""


def _period_line_from_spec_period_window(spec: dict[str, Any]) -> str:
    """Return a resolved period line for scenario labels backed by a window."""

    period_window = spec.get("period_window")
    if not isinstance(period_window, dict):
        return ""
    selected_periods = [
        str(period) for period in spec.get("selected_periods") or [] if period
    ]
    if not selected_periods or not any(
        is_scenario_label(period) for period in selected_periods
    ):
        return ""
    current_label = selected_periods[-1]
    previous_label = selected_periods[0] if len(selected_periods) > 1 else None
    recipe = {
        "options": {
            "period_window": period_window,
            "period_comparison_mode": spec.get("period_comparison_mode")
            or period_window.get("mode"),
        }
    }
    return reporting_period_line_from_recipe(
        recipe,
        current_label=current_label,
        previous_label=previous_label,
    )


def _replace_period_display_label(text: Any, spec: dict[str, Any]) -> str:
    """Replace an internal scenario code such as AC with a reader-facing label."""

    display_label = str(spec.get("period_display_label") or "").strip()
    if not display_label:
        return str(text or "")
    selected_periods = [
        str(period) for period in spec.get("selected_periods") or [] if period
    ]
    replaceable_labels = set(selected_periods)
    replaceable_labels.add(CURRENT_PERIOD)
    lines = _html_title_lines(text)
    if not lines:
        return str(text or "")
    last_line = _plain_title_text(lines[-1])
    if last_line not in replaceable_labels:
        return str(text or "")
    lines[-1] = html.escape(display_label)
    return "<br>".join(lines)


def _apply_period_display_label_to_titles(
    figures: list[Any], spec: dict[str, Any]
) -> None:
    """Apply explicit period-display labels to figure titles and title annotations."""

    if not str(spec.get("period_display_label") or "").strip():
        return
    for fig in figures:
        layout = getattr(fig, "layout", None)
        if layout is None:
            continue
        title = getattr(layout, "title", None)
        if title is not None:
            title.text = _replace_period_display_label(
                getattr(title, "text", ""),
                spec,
            )
        for annotation in _sequence(getattr(layout, "annotations", None)):
            if _is_period_window_title_annotation(annotation):
                annotation.text = _replace_period_display_label(
                    getattr(annotation, "text", ""),
                    spec,
                )


def _apply_period_window_axis_labels(
    figures: list[Any],
    period_adapter_audit: dict[str, Any],
) -> None:
    """Shorten visible period-window x-axis labels when title carries the cutoff."""

    mode = period_adapter_audit.get("period_comparison_mode")
    if mode not in {"year_to_date", "rolling_period"}:
        return
    for fig in figures:
        layout = getattr(fig, "layout", None)
        axis = getattr(layout, "xaxis", None) if layout is not None else None
        if axis is None:
            continue
        ticktext = list(_sequence(getattr(axis, "ticktext", None)))
        if not ticktext:
            continue
        changed = False
        replacement: list[Any] = []
        for label in ticktext:
            compact = _period_window_axis_year_label(label)
            if compact is None:
                replacement.append(label)
            else:
                replacement.append(compact)
                changed = True
        if changed:
            axis.ticktext = replacement
            axis.tickangle = 0


def _fallback_measure_line_for_spec(spec: dict[str, Any]) -> str:
    """Return a conservative measure/dimension line when legacy title parsing fails."""

    metric = str((spec.get("metrics") or [spec.get("metric") or "Sales"])[0])
    dimensions = [str(dimension) for dimension in spec.get("dimensions") or []]
    if dimensions:
        if len(dimensions) == 1:
            dimension_text = dimensions[0]
        else:
            dimension_text = ", ".join(dimensions[:-1]) + f" and {dimensions[-1]}"
        return f"<b>{html.escape(metric)}</b> in mEUR by {html.escape(dimension_text)}"
    return f"<b>{html.escape(metric)}</b> in mEUR"


def _population_title_note(spec: dict[str, Any]) -> str | None:
    """Return a short population note for filtered-population charts."""

    if str(spec.get("population_mode") or "") != "like_for_like":
        return None
    dimension = str(spec.get("population_dimension") or "").strip()
    if dimension:
        return f"Like-for-like {html.escape(dimension)} population"
    return "Like-for-like population"


def _append_population_note_to_measure_line(
    measure_line: str,
    spec: dict[str, Any],
) -> str:
    """Append a visible population qualifier to the reporting title."""

    note = _population_title_note(spec)
    if not note:
        return measure_line
    plain_line = _plain_title_text(measure_line).lower()
    if "like-for-like" in plain_line or "like for like" in plain_line:
        return measure_line
    return f"{measure_line} ({note})"


def _normalize_measure_line_html(line: str) -> str:
    """Repair legacy measure lines split across a stray bold tag boundary."""

    text = str(line or "").strip()
    if "</b>" not in text or "<b>" in text:
        return text
    text = text.replace("</b>", "", 1).strip()
    match = re.match(r"(?P<metric>[^<]+?)(?P<rest>\s+(?:in|by)\b.*)$", text)
    if not match:
        return html.escape(text)
    metric = match.group("metric").strip()
    rest = match.group("rest")
    return f"<b>{html.escape(metric)}</b>{html.escape(rest)}"


def _measure_line_for_reporting_title(
    text: str,
    lines: list[str],
    spec: dict[str, Any],
) -> str:
    """Return the measure/unit/dimension line from a legacy title."""

    for line in lines:
        plain = _plain_title_text(line).lower()
        if " by " in plain and (" in " in plain or "sales" in plain):
            return _normalize_measure_line_html(line)
    match = re.search(
        r"(<b>[^<]+</b>[^<]*(?:\s+by\s+[^<]+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return _normalize_measure_line_html(match.group(1).strip())
    return _fallback_measure_line_for_spec(spec)


def _compact_total_overlay_measure_line(
    measure_line: str,
    spec: dict[str, Any],
) -> str:
    """Drop redundant total-view wording from narrow overlay chart titles."""

    if not spec.get("plot_overlay_chart"):
        return measure_line
    dimensions = [str(item) for item in spec.get("dimensions") or []]
    if dimensions != [LEGACY_TOTAL_COLUMN_DIMENSION]:
        return measure_line
    return re.sub(
        rf"\s+by\s+{re.escape(LEGACY_TOTAL_COLUMN_DIMENSION)}\s*$",
        "",
        measure_line,
        flags=re.IGNORECASE,
    )


def _reporting_title_html_for_spec(
    selected_text: str,
    lines: list[str],
    spec: dict[str, Any],
    period_adapter_audit: dict[str, Any],
    entity: str,
) -> str:
    """Build the visible reporting title for a legacy mix chart."""

    metric_line = _compact_total_overlay_measure_line(
        _measure_line_for_reporting_title(selected_text, lines, spec),
        spec,
    )
    population_line = _population_title_note(spec)
    period_line = _period_line_for_reporting_title(
        lines,
        spec,
        period_adapter_audit,
    )
    if population_line:
        return "<br>".join(
            line
            for line in [
                html.escape(entity),
                metric_line,
                population_line,
                html.escape(period_line),
            ]
            if str(line or "").strip()
        )
    return reporting_title_html(
        html.escape(entity),
        metric_line,
        html.escape(period_line),
    )


def _apply_plotly_reporting_title(fig: Any, title_html: str) -> None:
    """Attach a left-aligned reporting title to a Plotly figure."""

    if not title_html:
        return
    update_layout = getattr(fig, "update_layout", None)
    if callable(update_layout):
        update_layout(title={"text": title_html, "x": 0.01, "xanchor": "left"})
        layout = getattr(fig, "layout", None)
        margin = getattr(layout, "margin", None) if layout is not None else None
        if margin is not None and hasattr(margin, "to_plotly_json"):
            margin_payload = dict(margin.to_plotly_json())
            margin_payload["t"] = max(int(margin_payload.get("t") or 0), 95)
            update_layout(margin=margin_payload)
        return
    layout = getattr(fig, "layout", None)
    title = getattr(layout, "title", None) if layout is not None else None
    if title is not None:
        title.text = title_html


def _apply_reporting_title_structure(
    figures: list[Any],
    spec: dict[str, Any],
    period_adapter_audit: dict[str, Any],
) -> None:
    """Force reporting charts into entity, measure/unit, period title lines."""

    entity = str(
        spec.get("reporting_subject_label")
        or spec.get("reporting_entity_label")
        or spec.get("reporting_entity")
        or ""
    ).strip()
    if not entity:
        return
    for fig in figures:
        layout = getattr(fig, "layout", None)
        if layout is None:
            continue
        title = getattr(layout, "title", None)
        title_text = str(getattr(title, "text", "") or "") if title else ""
        candidates: list[tuple[Any, str, list[str]]] = []
        if title_text:
            candidates.append((title, title_text, _html_title_lines(title_text)))
        for annotation in _sequence(getattr(layout, "annotations", None)):
            text = str(getattr(annotation, "text", "") or "")
            if _is_period_window_title_annotation(annotation):
                candidates.append((annotation, text, _html_title_lines(text)))
        target: Any | None = None
        lines: list[str] = []
        selected_text = ""
        for candidate_target, candidate_text, candidate_lines in candidates:
            measure_line = _measure_line_for_reporting_title(
                candidate_text,
                candidate_lines,
                spec,
            )
            if " by " in _plain_title_text(measure_line).lower():
                target = candidate_target
                selected_text = candidate_text
                lines = candidate_lines
                break
        if target is None and candidates:
            target, selected_text, lines = candidates[0]
        if target is None or not selected_text:
            _apply_plotly_reporting_title(
                fig,
                _reporting_title_html_for_spec(
                    "",
                    [],
                    spec,
                    period_adapter_audit,
                    entity,
                ),
            )
            continue
        if not lines:
            continue
        target.text = _reporting_title_html_for_spec(
            selected_text,
            lines,
            spec,
            period_adapter_audit,
            entity,
        )


def _apply_synthesis_dimension_labels(
    figures: list[Any], dimensions: list[str]
) -> None:
    """Show synthesis column headers as dimensions and item labels as items."""

    if not dimensions:
        return
    tick_values = [index + 0.5 for index in range(len(dimensions))]
    tick_text = [str(dimension) for dimension in dimensions]
    for fig in figures:
        if hasattr(fig, "update_xaxes"):
            fig.update_xaxes(
                tickmode="array",
                tickvals=tick_values,
                ticktext=tick_text,
                side="bottom",
                ticks="",
            )
        _add_synthesis_total_percent_labels(fig, tick_values)
        for trace in _sequence(getattr(fig, "data", None)):
            item = _strip_legacy_by_prefix(getattr(trace, "name", ""))
            trace.name = item
            x_values = _sequence(getattr(trace, "x", None))
            y_values = _sequence(getattr(trace, "y", None))
            text_values: list[str] = []
            for x_value, y_value in zip(x_values, y_values):
                try:
                    position = int(x_value)
                except (TypeError, ValueError):
                    position = -1
                share = _format_synthesis_share(y_value)
                text_values.append(f"{item} {share}" if share and position >= 0 else "")
            if text_values:
                trace.text = text_values


def _capture_context_payload(
    *,
    spec: dict[str, Any],
    chart: dict[str, Any],
    calls: list[dict[str, Any]],
    figures: list[Any],
    exports: list[dict[str, Any]],
    source_functions: list[str],
) -> dict[str, Any] | None:
    if not spec.get("capture_chart_data"):
        return None
    if spec.get("capture_figure") == "last":
        selected_calls = calls[-1:]
        selected_figures = figures[-1:]
    elif spec.get("capture_figure") == "first":
        selected_calls = calls[:1]
        selected_figures = figures[:1]
    else:
        selected_calls = calls
        selected_figures = figures
    primary_call = selected_calls[-1] if selected_calls else {}
    dimensions = [str(item) for item in spec.get("dimensions") or []]
    title_payload: dict[str, Any] = {}
    for figure in selected_figures:
        title_payload = _title_contract_payload(_title_lines_from_figure(figure))
        if title_payload:
            break
    payload = {
        "schema_version": "1.0",
        "chart": spec["name"],
        "legacy_chart": primary_call.get("legacy_chart"),
        "capture_policy": spec.get("capture_figure") or "all",
        "chart_data_source": (
            "legacy set_up_tab_for_show_or_download_chart input dataframe"
        ),
        "dimensions": dimensions,
        "x_dimension": spec.get("x_dimension"),
        "y_dimension": spec.get("y_dimension"),
        "small_multiples_dimension": spec.get("small_multiples_dimension"),
        "dimension_selection": spec.get("dimension_selection"),
        "stacked_pareto_mode": spec.get("stacked_pareto_mode"),
        "count_dimension": spec.get("count_dimension"),
        "aggregate_uniques_by_dimension": spec.get("aggregate_uniques_by_dimension"),
        "aggregate_uniques_dimension": spec.get("aggregate_uniques_dimension"),
        "population_mode": spec.get("population_mode"),
        "population_dimension": spec.get("population_dimension"),
        "focus_item": spec.get("focus_item"),
        "focus_dimension": spec.get("focus_dimension"),
        "focus_status": spec.get("focus_status"),
        "focus_reason": spec.get("focus_reason"),
        "metric": spec.get("metric"),
        "metrics": spec.get("metrics") or [],
        "selected_periods": spec.get("selected_periods") or [],
        "period_grain": spec.get("period_grain"),
        "period_window": spec.get("period_window") or {},
        "period_selection_mode": spec.get("period_selection_mode"),
        "period_comparison_mode": spec.get("period_comparison_mode"),
        "period_adapter": spec.get("period_adapter"),
        "palette_policy": (
            "uniform_rank_palette"
            if spec.get("synthesis_uniform_palette")
            else "legacy_dimension_shifted_palette"
        ),
        "source_functions": source_functions,
        "data_frame": primary_call.get("data_frame"),
        "derived_metrics": primary_call.get("derived_metrics"),
        "series_by_dimension": _series_rows_by_dimension(selected_figures, dimensions),
        "waterfall_rows": _waterfall_rows_from_figures(selected_figures),
        "captured_calls": selected_calls,
        "trace_widths": _context_trace_widths(selected_figures, spec),
        "plotly_figures": [_figure_payload(fig) for fig in selected_figures],
        "exports": exports,
        **title_payload,
    }
    if spec.get("related_metrics_bar"):
        related_rows, notable_mismatches = _related_metric_rows_from_figures(
            selected_figures,
            spec,
        )
        metrics = [str(item) for item in spec.get("metrics") or []]
        payload.update(
            {
                "primary_metric": metrics[0] if metrics else spec.get("metric"),
                "marker_metric": metrics[1] if len(metrics) > 1 else None,
                "related_metric_rows": related_rows,
                "notable_mismatches": notable_mismatches,
                "other_bucket_rows": [
                    row for row in related_rows if row.get("is_other_bucket")
                ],
            }
        )
    return payload


def _find_headless_chrome() -> str | None:
    configured = (
        os.environ.get("PLOTLY_CHROME_PATH")
        or os.environ.get("BROWSER_PATH")
        or os.environ.get("CHROME_PATH")
    )
    candidates = [
        configured,
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
        *HEADLESS_CHROME_CANDIDATES,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _axis_domains(layout: Any, prefix: str) -> set[tuple[float, float]]:
    """Return unique Plotly subplot domains for one axis family."""

    if layout is None or not hasattr(layout, "to_plotly_json"):
        return set()
    layout_json = layout.to_plotly_json()
    domains: set[tuple[float, float]] = set()
    for key, axis in layout_json.items():
        if not key.startswith(f"{prefix}axis") or not isinstance(axis, dict):
            continue
        domain = axis.get("domain")
        if not isinstance(domain, list) or len(domain) != 2:
            continue
        domains.add((round(float(domain[0]), 6), round(float(domain[1]), 6)))
    return domains


def _subplot_grid_size(fig: Any) -> tuple[int, int]:
    """Infer the Plotly subplot grid size without changing legacy chart code."""

    layout = getattr(fig, "layout", None)
    columns = max(len(_axis_domains(layout, "x")), 1)
    rows = max(len(_axis_domains(layout, "y")), 1)
    return columns, rows


def _has_vertical_bar_trace(fig: Any) -> bool:
    """Return True when a figure contains vertical bar/column traces."""

    for trace in _sequence(getattr(fig, "data", None)):
        if str(getattr(trace, "type", "") or "") != "bar":
            continue
        if str(getattr(trace, "orientation", "") or "v").lower() == "h":
            continue
        return True
    return False


def _has_horizontal_bar_trace(fig: Any) -> bool:
    """Return True when a figure contains horizontal bar traces."""

    for trace in _sequence(getattr(fig, "data", None)):
        if str(getattr(trace, "type", "") or "") != "bar":
            continue
        if str(getattr(trace, "orientation", "") or "v").lower() == "h":
            return True
    return False


def _legacy_export_size(fig: Any, artifact_name: str | None = None) -> tuple[int, int]:
    """Choose a readable export canvas for captured legacy Plotly figures."""

    layout = getattr(fig, "layout", None)
    layout_width = int(getattr(layout, "width", 0) or 0)
    layout_height = int(getattr(layout, "height", 0) or 0)
    columns, rows = _subplot_grid_size(fig)
    if columns * rows > 1:
        if _is_barmekko_small_multiple_artifact(artifact_name):
            return (
                max(layout_width, BARMEEKKO_SMALL_MULTIPLE_MIN_WIDTH),
                max(layout_height, BARMEEKKO_SMALL_MULTIPLE_MIN_HEIGHT),
            )
        if layout_width > 0 and layout_height > 0 and _has_horizontal_bar_trace(fig):
            return layout_width, layout_height
        width = max(layout_width, 420 + columns * 900)
        height = max(layout_height, 260 + rows * 520)
        return min(width, 2600), min(height, 2400)
    if layout_width > 0 and layout_height > 0:
        if (
            layout_width <= LEGACY_NARROW_VERTICAL_BAR_MAX_WIDTH
            and _has_vertical_bar_trace(fig)
        ):
            return (
                layout_width + LEGACY_NARROW_VERTICAL_BAR_RIGHT_PADDING,
                layout_height,
            )
        return layout_width, layout_height
    return max(layout_width, 1400), max(layout_height, 900)


def _preserve_legacy_single_panel_plot_width(
    fig: Any, original_width: int, export_width: int
) -> None:
    """Keep narrow legacy columns from stretching when export canvas gets padding."""

    if export_width <= original_width or original_width <= 0:
        return
    if not _has_vertical_bar_trace(fig):
        return
    if _subplot_grid_size(fig) != (1, 1):
        return
    domain_end = max(min(original_width / export_width, 1.0), 0.1)
    try:
        fig.update_xaxes(domain=[0.0, domain_end])
    except (AttributeError, TypeError, ValueError):
        return


def _write_plotly_html(fig: Any, path: Path, width: int, height: int) -> Path:
    html_path = path.with_suffix(".html")
    fig.write_html(
        str(html_path),
        include_plotlyjs=True,
        full_html=True,
        default_width=f"{width}px",
        default_height=f"{height}px",
    )
    return html_path


def _static_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Return a readable font for browserless static chart fallbacks."""

    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_static_title_lines(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    *,
    x: int,
    y: int,
    line_height: int,
    font: ImageFont.ImageFont,
    max_lines: int | None = None,
) -> None:
    """Draw fallback title lines with one normal title font."""

    title_lines = list(lines if max_lines is None else lines[:max_lines])
    for line_index, line in enumerate(title_lines):
        draw.text(
            (x, y + (line_index * line_height)),
            line,
            fill="#2F3437",
            font=font,
        )


def _strip_plotly_html(value: Any) -> str:
    """Return compact text from a Plotly title or annotation string."""

    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _static_compact_number(value: float) -> str:
    """Return a compact numeric label for static chart fallbacks."""

    number = float(value or 0.0)
    abs_number = abs(number)
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs_number >= 1_000:
        return f"{number / 1_000:.1f}K"
    if abs(number - round(number)) < 0.05:
        return f"{int(round(number))}"
    return f"{number:.1f}"


def _static_trace_color(trace: Any, fallback: str) -> str:
    """Return a usable hex/rgb color from a Plotly trace."""

    marker = getattr(trace, "marker", None)
    color = getattr(marker, "color", None) if marker is not None else None
    if isinstance(color, str) and color.strip():
        return color
    if isinstance(color, list) and color:
        first = color[0]
        if isinstance(first, str) and first.strip():
            return first
    return fallback


def _static_float(value: Any) -> float | None:
    """Return a float for numeric Plotly coordinates, otherwise None."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _static_trace_number_at(value: Any, index: int, default: float = 0.0) -> float:
    """Return a scalar-or-sequence Plotly numeric attribute at ``index``."""

    values = _sequence(value)
    if not values:
        return default
    selected = values[index] if index < len(values) else values[0]
    numeric = _static_float(selected)
    return default if numeric is None else numeric


def _static_axis_tick_labels(fig: Any) -> list[tuple[float, str]]:
    """Return non-blank x-axis tick positions and labels from a Plotly layout."""

    layout = getattr(fig, "layout", None)
    axis = getattr(layout, "xaxis", None) if layout is not None else None
    if axis is None:
        return []
    tickvals = _sequence(getattr(axis, "tickvals", None))
    ticktext = _sequence(getattr(axis, "ticktext", None))
    labels: list[tuple[float, str]] = []
    for index, tick in enumerate(tickvals):
        numeric = _static_float(tick)
        if numeric is None:
            continue
        label = str(tick)
        if index < len(ticktext):
            label = _strip_plotly_html(ticktext[index])
        if label.strip():
            labels.append((numeric, label.strip()))
    return labels


def _static_axis_label_for_coord(
    axis_labels: list[tuple[float, str]],
    coord: float | None,
    fallback: Any,
) -> str:
    """Return the closest legacy axis label for a plotted x-coordinate."""

    if coord is not None and axis_labels:
        closest = min(axis_labels, key=lambda item: abs(item[0] - coord))
        if abs(closest[0] - coord) <= 0.51:
            return closest[1]
    return str(fallback)


def _static_bar_coord(trace: Any, index: int, x_value: Any) -> float | None:
    """Return the visual center coordinate for a vertical Plotly bar point."""

    raw = _static_float(x_value)
    if raw is None:
        return None
    offset = _static_trace_number_at(getattr(trace, "offset", None), index, 0.0)
    width = _static_trace_number_at(getattr(trace, "width", None), index, 0.0)
    return raw + offset + (width / 2.0)


def _static_category_key(coord: float | None, label: str) -> str:
    """Return a stable key for a static fallback category."""

    if coord is None:
        return f"label:{label}"
    return f"coord:{coord:.6f}"


def _static_trace_texts(trace: Any) -> list[str]:
    """Return cleaned per-point text labels from a Plotly trace."""

    return [
        _strip_plotly_html(value) for value in _sequence(getattr(trace, "text", None))
    ]


def _static_title_lines(fig: Any) -> list[str]:
    """Return legacy title lines from layout title or annotations."""

    layout = getattr(fig, "layout", None)
    candidates: list[str] = []
    title_text = getattr(getattr(layout, "title", None), "text", "") if layout else ""
    if title_text:
        candidates.append(str(title_text))
    for annotation in _sequence(
        getattr(layout, "annotations", None) if layout else None
    ):
        xref = str(getattr(annotation, "xref", "") or "")
        yref = str(getattr(annotation, "yref", "") or "")
        text = str(getattr(annotation, "text", "") or "")
        if xref == "paper" and yref == "paper" and text:
            cleaned = _strip_plotly_html(text)
            if cleaned and "CAGR" not in cleaned:
                candidates.append(text)
    for candidate in candidates:
        lines = [
            line.strip()
            for line in _strip_plotly_html(candidate).splitlines()
            if line.strip()
        ]
        if lines:
            return lines[:3]
    return []


def _static_total_labels(
    fig: Any,
    categories: list[dict[str, Any]],
) -> dict[str, str]:
    """Return legacy top labels keyed by static category key."""

    labels: dict[str, str] = {}
    coords = [
        (category["key"], category.get("coord"))
        for category in categories
        if category.get("coord") is not None
    ]
    layout = getattr(fig, "layout", None)
    for annotation in _sequence(
        getattr(layout, "annotations", None) if layout else None
    ):
        if str(getattr(annotation, "xref", "") or "") != "x":
            continue
        yref = str(getattr(annotation, "yref", "") or "")
        if yref not in {"y", "paper"}:
            continue
        if yref == "paper":
            annotation_y = _static_float(getattr(annotation, "y", None))
            if annotation_y is None or abs(annotation_y - 1.0) > 0.05:
                continue
        text = _strip_plotly_html(getattr(annotation, "text", ""))
        if not text:
            continue
        annotation_x = _static_float(getattr(annotation, "x", None))
        if annotation_x is None or not coords:
            continue
        key, coord = min(coords, key=lambda item: abs(float(item[1]) - annotation_x))
        if coord is not None and abs(float(coord) - annotation_x) <= 0.51:
            labels[key] = text
    return labels


def _format_compact_total_value(value: Any) -> str:
    """Return compact decimal total with an explicit magnitude suffix."""

    if value is None:
        return ""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return str(value)
    abs_value = abs(numeric_value)
    for scale, suffix in (
        (1_000_000_000, "bn"),
        (1_000_000, "m"),
        (1_000, "k"),
    ):
        if abs_value >= scale:
            return f"{numeric_value / scale:.1f}{suffix}"
    if float(numeric_value).is_integer():
        return str(int(numeric_value))
    return f"{numeric_value:.1f}"


def _format_stacked_pareto_total_label(
    value: Any,
    metric_label: str,
    chart_dict: dict[str, Any],
    names: dict[str, str],
    count_by_column: str,
) -> str:
    """Return a self-describing compact total for stacked Pareto columns."""

    del metric_label, chart_dict, names, count_by_column
    return _format_compact_total_value(value)


def _format_stacked_pareto_axis_label(
    metric_label: str,
    chart_dict: dict[str, Any],
    names: dict[str, str],
    count_by_column: str,
) -> str:
    """Return a compact self-describing x-axis label for stacked Pareto columns."""

    metric_text = str(metric_label)
    count_text = str(count_by_column)
    if metric_text == count_text or metric_text.startswith(f"{names['countName']} "):
        count_label = str(chart_dict.get(names["countColumn"]) or metric_text)
        cleaned = re.sub(
            r"^(#\s*of|count\s+by)\s+",
            "",
            count_label.strip(),
            flags=re.I,
        )
        return (
            f"# of<br>{html.escape(cleaned)}" if cleaned else html.escape(metric_text)
        )
    if metric_text.lower() == str(names["unitsName"]).lower():
        return html.escape(metric_text)
    currency = str(
        chart_dict.get(names["fullCurrencyName"])
        or chart_dict.get(names["currencyChoice"])
        or ""
    ).strip()
    if currency:
        return f"{html.escape(metric_text)}<br>{html.escape(currency)}"
    return html.escape(metric_text)


def _stacked_pareto_axis_labels(
    metric_names: list[str],
    count_by_column: str,
    chart_dict: dict[str, Any],
    names: dict[str, str],
) -> list[str]:
    """Return x-axis labels for metric and count columns."""

    return [
        _format_stacked_pareto_axis_label(
            metric_label,
            chart_dict,
            names,
            count_by_column,
        )
        for metric_label in [*metric_names, str(count_by_column)]
    ]


def _stacked_pareto_metric_order(
    chart_dict: dict[str, Any],
    names: dict[str, str],
) -> list[str]:
    """Return the row order expected by the stacked Pareto splitter."""

    metric_names = [str(item) for item in chart_dict.get(names["metricsToPlot"], [])]
    count_by_column = chart_dict.get(names["countByColumn"]) or (
        f"{names['countName']} {chart_dict.get(names['countColumn'])}"
    )
    data_metrics: list[str] = []
    if chart_dict.get(names["showMetricsInDataColumn"]):
        data_metrics = [
            str(item)
            for item in chart_dict.get(names["metricsToShowInDataColumn"], [])
            if item
        ]
    order = [
        *metric_names,
        str(count_by_column),
        *data_metrics,
        names["workColumn"],
    ]
    return [item for item in dict.fromkeys(order) if item]


def _apply_stacked_pareto_axis_labels(figure: Any, labels: list[str]) -> Any:
    """Apply safer stacked Pareto x-axis labels when tick count matches."""

    axis = getattr(getattr(figure, "layout", None), "xaxis", None)
    ticktext = getattr(axis, "ticktext", None) if axis is not None else None
    if not labels or ticktext is None or len(ticktext) != len(labels):
        return figure
    axis.ticktext = labels
    return figure


def _stacked_pareto_total_x_positions(figure: Any, count: int) -> list[float]:
    """Return x-axis centers for stacked Pareto total annotations."""

    axis = getattr(getattr(figure, "layout", None), "xaxis", None)
    tickvals = list(getattr(axis, "tickvals", []) or [])
    positions: list[float] = []
    for value in tickvals[:count]:
        numeric = _static_float(value)
        if numeric is None:
            return [index + 0.5 for index in range(count)]
        positions.append(numeric)
    if len(positions) == count:
        return positions
    return [index + 0.5 for index in range(count)]


def _stacked_pareto_marker_column(frame: pl.DataFrame) -> str | None:
    """Return the metric-label column from a transposed stacked Pareto frame."""

    columns = LegacyPreparedDataCache._columns(frame)
    if not columns:
        return None
    if STACKED_PARETO_METRIC_LABEL_COLUMN in columns:
        return STACKED_PARETO_METRIC_LABEL_COLUMN
    return columns[0]


def _stacked_pareto_row_by_label(
    frame: pl.DataFrame,
    marker_column: str,
    label: str,
) -> dict[str, Any] | None:
    """Return the first row whose marker matches ``label``."""

    if marker_column not in LegacyPreparedDataCache._columns(frame):
        return None
    rows = frame.filter(pl.col(marker_column).cast(pl.Utf8) == str(label)).to_dicts()
    return rows[0] if rows else None


def _stacked_pareto_readable_side_segment(value: Any) -> bool:
    """Return whether a side metric label has enough vertical room."""

    numeric = _static_float(value)
    return numeric is not None and abs(numeric) >= 0.035


def _stacked_pareto_side_metric_x(figure: Any) -> float:
    """Return an x coordinate just to the right of the last visible column."""

    right_edges: list[float] = []
    for trace in _sequence(getattr(figure, "data", None)):
        x_values = _sequence(getattr(trace, "x", None))
        if not x_values:
            continue
        index = len(x_values) - 1
        x_value = _static_float(x_values[index])
        if x_value is None:
            continue
        offset = _static_trace_number_at(getattr(trace, "offset", None), index, 0.0)
        width = _static_trace_number_at(getattr(trace, "width", None), index, 0.9)
        right_edges.append(x_value + offset + width + 0.12)
    if right_edges:
        return max(right_edges)
    positions = _stacked_pareto_total_x_positions(figure, 1)
    return (positions[-1] if positions else 2.5) + 0.55


def _stacked_pareto_unit_price_payload(
    df: pl.DataFrame | pl.LazyFrame,
    chart_dict: dict[str, Any],
    names: dict[str, str],
) -> dict[str, Any] | None:
    """Return Unit Price values by visible stacked Pareto segment."""

    metric_names = [str(item) for item in chart_dict.get(names["metricsToPlot"], [])]
    if names["monetaryLocalCurrencyName"] not in metric_names:
        return None
    if names["unitsName"] not in metric_names:
        return None
    frame = LegacyPreparedDataCache._collect_frame(df)
    marker_column = _stacked_pareto_marker_column(frame)
    if marker_column is None:
        return None
    sales_row = _stacked_pareto_row_by_label(
        frame, marker_column, names["monetaryLocalCurrencyName"]
    )
    units_row = _stacked_pareto_row_by_label(frame, marker_column, names["unitsName"])
    count_by_column = chart_dict.get(names["countByColumn"]) or (
        f"{names['countName']} {chart_dict.get(names['countColumn'])}"
    )
    count_row = _stacked_pareto_row_by_label(frame, marker_column, str(count_by_column))
    if sales_row is None or units_row is None:
        return None
    total_sales = _static_float(sales_row.get(names["valueName"]))
    total_units = _static_float(sales_row.get(names["unitsName"]))
    if total_sales is None or total_units in (None, 0):
        return None
    segment_columns = [
        column
        for column in LegacyPreparedDataCache._columns(frame)
        if column
        not in {
            marker_column,
            names["valueName"],
            names["unitsName"],
            str(count_by_column),
            names["workColumn"],
        }
    ]
    segments: list[dict[str, Any]] = []
    running = 0.0
    for segment in segment_columns:
        sales_share = _static_float(sales_row.get(segment))
        units_share = _static_float(units_row.get(segment))
        stack_share = _static_float(
            (count_row or sales_row).get(segment) if (count_row or sales_row) else None
        )
        if stack_share is None:
            stack_share = sales_share or 0.0
        midpoint = running + (stack_share / 2.0)
        running += stack_share
        if (
            sales_share is None
            or units_share in (None, 0)
            or not _stacked_pareto_readable_side_segment(stack_share)
        ):
            continue
        value = (sales_share * total_sales) / (units_share * total_units)
        segments.append(
            {
                "item": str(segment),
                "metric": names["pricePerUnitName"],
                "value": value,
                "text": _format_compact_total_value(round(value, 1)),
                "reference_share": stack_share,
                "y": midpoint,
            }
        )
    if not segments:
        return None
    total_value = total_sales / total_units
    return {
        "metric": names["pricePerUnitName"],
        "total": total_value,
        "total_text": _format_compact_total_value(round(total_value, 1)),
        "segments": segments,
    }


def _add_stacked_pareto_side_metric_annotations(
    figure: Any,
    df: pl.DataFrame | pl.LazyFrame,
    chart_dict: dict[str, Any],
    names: dict[str, str],
) -> Any:
    """Add legacy-style side metric annotations to stacked Pareto charts."""

    payload = _stacked_pareto_unit_price_payload(df, chart_dict, names)
    if payload is None:
        return figure
    x_value = _stacked_pareto_side_metric_x(figure)
    try:
        figure.update_xaxes(range=[-0.15, x_value + 0.75])
    except (AttributeError, TypeError, ValueError):
        pass
    figure.add_annotation(
        text=f"{html.escape(str(payload['metric']))}<br>{payload['total_text']}",
        showarrow=False,
        align="left",
        x=x_value,
        xref="x",
        xanchor="left",
        y=1,
        yref="paper",
        yshift=8,
        font={"size": 12},
    )
    for segment in payload["segments"]:
        figure.add_annotation(
            text=str(segment["text"]),
            showarrow=False,
            align="left",
            x=x_value,
            xref="x",
            xanchor="left",
            y=segment["y"],
            yref="y",
            font={"size": 12},
        )
    return figure


def _static_nearest_category_key(
    categories: list[dict[str, Any]],
    x_value: Any,
) -> str | None:
    """Return the category key nearest to a Plotly x value."""

    numeric = _static_float(x_value)
    if numeric is not None:
        numeric_categories = [
            category for category in categories if category.get("coord") is not None
        ]
        if numeric_categories:
            closest = min(
                numeric_categories,
                key=lambda category: abs(float(category["coord"]) - numeric),
            )
            if abs(float(closest["coord"]) - numeric) <= 0.51:
                return str(closest["key"])
    label = str(x_value)
    for category in categories:
        if str(category.get("label")) == label:
            return str(category["key"])
    return None


def _static_text_width(font: ImageFont.ImageFont, text: str) -> int:
    """Return approximate rendered text width for a PIL font."""

    box = font.getbbox(text)
    return int(box[2] - box[0])


def _static_ellipsize(
    text: str,
    max_width: float,
    font: ImageFont.ImageFont,
) -> str:
    """Return text shortened to fit the available width."""

    if _static_text_width(font, text) <= max_width:
        return text
    suffix = "..."
    if _static_text_width(font, suffix) > max_width:
        return ""
    shortened = text
    while shortened and _static_text_width(font, f"{shortened}{suffix}") > max_width:
        shortened = shortened[:-1].rstrip()
    return f"{shortened}{suffix}" if shortened else suffix


def _static_ellipsize_preserve_suffix(
    text: str,
    max_width: float,
    font: ImageFont.ImageFont,
) -> str:
    """Shorten a label while preserving a trailing numeric suffix when possible."""

    if _static_text_width(font, text) <= max_width:
        return text
    match = re.search(r"\s+(-?\d+(?:[.,]\d+)?%?)$", text)
    if not match:
        return _static_ellipsize(text, max_width, font)
    suffix = match.group(1)
    prefix = text[: match.start()].rstrip()
    suffix_width = _static_text_width(font, f" {suffix}")
    prefix_width = max_width - suffix_width
    if prefix_width <= _static_text_width(font, "..."):
        return suffix if _static_text_width(font, suffix) <= max_width else ""
    shortened_prefix = _static_ellipsize(prefix, prefix_width, font)
    return f"{shortened_prefix} {suffix}" if shortened_prefix else suffix


def _static_fit_synthesis_label_lines(
    text: str,
    max_width: float,
    max_height: float,
    font: ImageFont.ImageFont,
) -> list[str]:
    """Return one or two inside-label lines for synthesis stacked columns."""

    if max_width <= 0 or max_height <= 0:
        return []
    text_box = font.getbbox(text)
    line_height = text_box[3] - text_box[1]
    if _static_text_width(font, text) <= max_width and line_height <= max_height:
        return [text]
    match = re.search(r"\s+(-?\d+(?:[.,]\d+)?%?)$", text)
    if match and max_height >= (line_height * 2) + 3:
        suffix = match.group(1)
        prefix = text[: match.start()].rstrip()
        prefix_line = _static_ellipsize(prefix, max_width, font)
        if (
            prefix_line
            and _static_text_width(font, suffix) <= max_width
            and prefix_line != "..."
        ):
            return [prefix_line, suffix]
    single_line = _static_ellipsize_preserve_suffix(text, max_width, font)
    if single_line and line_height <= max_height:
        return [single_line]
    return []


def _static_column_payload(fig: Any) -> dict[str, Any] | None:
    """Return simple vertical column data from a Plotly figure when possible."""

    bars: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    category_keys: set[str] = set()
    axis_labels = _static_axis_tick_labels(fig)
    palette = [
        "#333333",
        "#9E9E9E",
        "#606060",
        "#9FB1BF",
        "#D9D9D9",
        "#B03A85",
        "#6F8799",
    ]
    for trace in _sequence(getattr(fig, "data", None)):
        trace_type = str(getattr(trace, "type", "") or "")
        if trace_type == "bar":
            if str(getattr(trace, "orientation", "") or "v").lower() == "h":
                return None
            raw_x = _sequence(getattr(trace, "x", None))
            raw_y = _sequence(getattr(trace, "y", None))
            if not raw_y:
                continue
            if not raw_x:
                raw_x = list(range(1, len(raw_y) + 1))
            raw_text = _static_trace_texts(trace)
            values: dict[str, float] = {}
            texts: dict[str, str] = {}
            for index, (x_value, y_value) in enumerate(zip(raw_x, raw_y)):
                try:
                    numeric = float(y_value)
                except (TypeError, ValueError):
                    continue
                if numeric <= 0:
                    continue
                coord = _static_bar_coord(trace, index, x_value)
                label = _static_axis_label_for_coord(axis_labels, coord, x_value)
                key = _static_category_key(coord, label)
                if key not in category_keys:
                    categories.append({"key": key, "label": label, "coord": coord})
                    category_keys.add(key)
                values[key] = numeric
                if index < len(raw_text) and raw_text[index]:
                    texts[key] = raw_text[index]
            bars.append(
                {
                    "name": str(getattr(trace, "name", "") or ""),
                    "values": values,
                    "texts": texts,
                    "color": _static_trace_color(
                        trace,
                        palette[len(bars) % len(palette)],
                    ),
                }
            )
        elif trace_type == "scatter":
            raw_x = _sequence(getattr(trace, "x", None))
            raw_y = _sequence(getattr(trace, "y", None))
            if not raw_x or not raw_y:
                continue
            raw_text = _static_trace_texts(trace)
            points: list[tuple[str, float, str | None]] = []
            for index, (x_value, y_value) in enumerate(zip(raw_x, raw_y)):
                try:
                    numeric = float(y_value)
                except (TypeError, ValueError):
                    continue
                key = _static_nearest_category_key(categories, x_value)
                if key is None:
                    continue
                text = (
                    raw_text[index]
                    if index < len(raw_text) and raw_text[index]
                    else None
                )
                points.append((key, numeric, text))
            if points:
                lines.append(
                    {
                        "name": str(getattr(trace, "name", "") or ""),
                        "points": points,
                        "color": _static_trace_color(trace, "#D71920"),
                    }
                )
    if not bars or not categories:
        return None
    if len(categories) > 12:
        return None
    return {
        "categories": categories,
        "bars": bars,
        "lines": lines,
        "title_lines": _static_title_lines(fig),
        "total_labels": _static_total_labels(fig, categories),
    }


def _write_static_column_png(
    fig: Any,
    path: Path,
    width: int,
    height: int,
) -> str | None:
    """Write a deterministic PNG for simple column/stacked-column figures."""

    payload = _static_column_payload(fig)
    if payload is None:
        return "Figure is not a simple vertical column chart."

    categories = payload["categories"]
    bars = payload["bars"]
    lines = payload["lines"]
    total_labels = payload["total_labels"]
    is_dimension_synthesis = len(categories) >= 2 and all(
        (total_labels.get(str(category.get("key") or "")) or "")
        == SYNTHESIS_TOTAL_PERCENT_LABEL
        for category in categories
    )
    width = max(int(width), 900)
    height = max(int(height), 650)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _static_font(15)
    label_font = _static_font(19)
    small_font = _static_font(15)
    value_font = _static_font(17, bold=True)
    synthesis_value_font = _static_font(8, bold=False)

    _draw_static_title_lines(
        draw,
        payload["title_lines"],
        x=58,
        y=32,
        line_height=30,
        font=title_font,
    )

    left = 120
    right = 80 if is_dimension_synthesis else (245 if len(bars) > 1 else 110)
    top = 145
    bottom = 92
    plot_width = width - left - right
    plot_height = height - top - bottom
    totals = [
        sum(
            max(0.0, float(series["values"].get(category["key"], 0.0)))
            for series in bars
        )
        for category in categories
    ]
    max_total = max(totals) if totals else 0.0
    if max_total <= 0:
        return "Column chart has no positive values."

    axis_y = top + plot_height
    draw.line((left, axis_y, left + plot_width, axis_y), fill="#D9D9D9", width=1)
    slot_width = plot_width / max(len(categories), 1)
    bar_width = (
        min(126.0, max(70.0, slot_width * 0.82))
        if is_dimension_synthesis
        else min(96.0, max(44.0, slot_width * 0.34))
    )
    x_centers = {
        category["key"]: left + (slot_width * (index + 0.5))
        for index, category in enumerate(categories)
    }
    scale = plot_height / (max_total * 1.12)

    for x_index, category in enumerate(categories):
        category_key = category["key"]
        category_label = category["label"]
        x_center = x_centers[category_key]
        x0 = int(x_center - (bar_width / 2))
        x1 = int(x_center + (bar_width / 2))
        running = 0.0
        for series in bars:
            value = max(0.0, float(series["values"].get(category_key, 0.0)))
            if value <= 0:
                continue
            y0 = int(axis_y - ((running + value) * scale))
            y1 = int(axis_y - (running * scale))
            draw.rectangle((x0, y0, x1, y1), fill=str(series["color"]))
            label_share = value / max(totals[x_index], 1.0)
            if label_share >= (0.06 if is_dimension_synthesis else 0.08):
                text = series["texts"].get(category_key) or _static_compact_number(
                    value
                )
                segment_font = (
                    synthesis_value_font if is_dimension_synthesis else value_font
                )
                if is_dimension_synthesis:
                    label_lines = _static_fit_synthesis_label_lines(
                        text,
                        max(0.0, (x1 - x0) - 10),
                        max(0.0, (y1 - y0) - 4),
                        synthesis_value_font,
                    )
                    if not label_lines:
                        running += value
                        continue
                    line_boxes = [
                        draw.textbbox((0, 0), line, font=synthesis_value_font)
                        for line in label_lines
                    ]
                    line_heights = [box[3] - box[1] for box in line_boxes]
                    total_height = sum(line_heights) + (3 * (len(label_lines) - 1))
                    line_y = y0 + ((y1 - y0 - total_height) / 2)
                    for line, line_box, line_height in zip(
                        label_lines,
                        line_boxes,
                        line_heights,
                        strict=True,
                    ):
                        draw.text(
                            (
                                x_center - ((line_box[2] - line_box[0]) / 2),
                                line_y,
                            ),
                            line,
                            fill="white",
                            font=synthesis_value_font,
                        )
                        line_y += line_height + 3
                else:
                    text_box = draw.textbbox((0, 0), text, font=segment_font)
                    if (text_box[3] - text_box[1]) > (y1 - y0 - 4):
                        running += value
                        continue
                    draw.text(
                        (
                            x_center - ((text_box[2] - text_box[0]) / 2),
                            y0 + ((y1 - y0 - (text_box[3] - text_box[1])) / 2),
                        ),
                        text,
                        fill="white",
                        font=segment_font,
                    )
            running += value
        total_text = total_labels.get(category_key) or (
            SYNTHESIS_TOTAL_PERCENT_LABEL
            if is_dimension_synthesis
            else _static_compact_number(totals[x_index])
        )
        total_box = draw.textbbox((0, 0), total_text, font=value_font)
        draw.text(
            (
                x_center - ((total_box[2] - total_box[0]) / 2),
                int(axis_y - totals[x_index] * scale) - 28,
            ),
            total_text,
            fill="#222222",
            font=value_font,
        )
        label_box = draw.textbbox((0, 0), category_label, font=label_font)
        draw.text(
            (
                x_center - ((label_box[2] - label_box[0]) / 2),
                axis_y + 13,
            ),
            category_label,
            fill="#2F3437",
            font=label_font,
        )

    if len(bars) > 1 and not is_dimension_synthesis:
        last_key = categories[-1]["key"]
        running = 0.0
        label_x = left + plot_width + 24
        label_rows: list[tuple[float, str]] = []
        for series in bars:
            value = max(0.0, float(series["values"].get(last_key, 0.0)))
            if value <= 0:
                continue
            center_y = axis_y - ((running + (value / 2.0)) * scale)
            label_rows.append((center_y, str(series["name"])))
            running += value
        label_rows.sort(key=lambda item: item[0])
        label_positions = [row[0] for row in label_rows]
        min_gap = 20.0
        for index in range(1, len(label_positions)):
            label_positions[index] = max(
                label_positions[index],
                label_positions[index - 1] + min_gap,
            )
        if label_positions:
            overflow = label_positions[-1] - (axis_y - 12)
            if overflow > 0:
                label_positions = [position - overflow for position in label_positions]
            for index in range(1, len(label_positions)):
                label_positions[index] = max(
                    label_positions[index],
                    label_positions[index - 1] + min_gap,
                )
        for (center_y, label), label_y in zip(label_rows, label_positions):
            draw.line(
                (
                    int(x_centers[last_key] + (bar_width / 2)) + 4,
                    int(center_y),
                    label_x - 6,
                    int(label_y),
                ),
                fill="#D0D0D0",
                width=1,
            )
            draw.text(
                (label_x, int(label_y) - 9),
                label,
                fill="#333333",
                font=small_font,
            )

    for line in lines:
        points: list[tuple[int, int, float, str | None]] = []
        values = [point[1] for point in line["points"]]
        max_line = max(values) if values else 0.0
        if max_line <= 0:
            continue
        for category_key, value, text in line["points"]:
            if category_key not in x_centers:
                continue
            x = int(x_centers[category_key])
            y = int(axis_y - ((value / (max_line * 1.12)) * plot_height))
            points.append((x, y, value, text))
        if len(points) >= 2:
            draw.line(
                [(x, y) for x, y, _value, _text in points],
                fill=str(line["color"]),
                width=2,
            )
        for x, y, value, text in points:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=str(line["color"]))
            draw.text(
                (x + 7, y - 18),
                text or _static_compact_number(value),
                fill=str(line["color"]),
                font=small_font,
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return None


def _static_horizontal_bar_payload(fig: Any) -> dict[str, Any] | None:
    """Return simple horizontal bar data from a Plotly figure when possible."""

    bar_traces: list[Any] = []
    marker_trace: Any | None = None
    for trace in _sequence(getattr(fig, "data", None)):
        trace_type = str(getattr(trace, "type", "") or "")
        orientation = str(getattr(trace, "orientation", "") or "").lower()
        mode = str(getattr(trace, "mode", "") or "")
        if trace_type == "bar" and orientation == "h":
            bar_traces.append(trace)
        elif trace_type == "scatter" and "markers" in mode:
            if marker_trace is not None:
                return None
            marker_trace = trace
    if not bar_traces:
        return None

    rows_by_label: dict[str, dict[str, Any]] = {}
    row_order: list[str] = []
    for trace_index, trace in enumerate(bar_traces):
        raw_x = _sequence(getattr(trace, "x", None))
        raw_y = _sequence(getattr(trace, "y", None))
        raw_text = _static_trace_texts(trace)
        trace_name = _strip_plotly_html(getattr(trace, "name", ""))
        trace_color = _static_trace_color(
            trace,
            "#333333" if trace_index == 0 else "#9E9E9E",
        )
        for index, (x_value, y_value) in enumerate(zip(raw_x, raw_y)):
            value = _static_float(x_value)
            if value is None or value <= 0 or y_value is None:
                continue
            label = _strip_plotly_html(y_value).replace("\u2063", "").strip()
            if not label or label.lower() == "none":
                continue
            if label not in rows_by_label:
                rows_by_label[label] = {
                    "label": label,
                    "segments": [],
                    "value": 0.0,
                }
                row_order.append(label)
            text = raw_text[index] if index < len(raw_text) else ""
            rows_by_label[label]["segments"].append(
                {
                    "name": trace_name,
                    "value": value,
                    "text": text,
                    "color": trace_color,
                }
            )
            rows_by_label[label]["value"] += value

    rows: list[dict[str, Any]] = []
    for label in row_order:
        row = rows_by_label[label]
        if len(row["segments"]) != len(bar_traces):
            return None
        rows.append(row)
    if not rows:
        return None

    annotations_by_label: dict[str, str] = {}
    total_label: str | None = None
    layout = getattr(fig, "layout", None)
    for annotation in _sequence(
        getattr(layout, "annotations", None) if layout else None
    ):
        text = _strip_plotly_html(getattr(annotation, "text", ""))
        if not text:
            continue
        if text.lower().startswith("total"):
            total_label = text
            continue
        y_value = getattr(annotation, "y", None)
        y_label = _strip_plotly_html(y_value).replace("\u2063", "").strip()
        if (
            y_label
            and y_label in rows_by_label
            and _looks_like_related_metric_value_label(text)
        ):
            annotations_by_label[y_label] = text

    markers_by_label: dict[str, dict[str, Any]] = {}
    if marker_trace is not None:
        marker_x = _sequence(getattr(marker_trace, "x", None))
        marker_y = _sequence(getattr(marker_trace, "y", None))
        marker_text = _static_trace_texts(marker_trace)
        for index, (x_value, y_value) in enumerate(zip(marker_x, marker_y)):
            value = _static_float(x_value)
            label = _strip_plotly_html(y_value).replace("\u2063", "").strip()
            if value is None or not label or label not in rows_by_label:
                continue
            markers_by_label[label] = {
                "value": value,
                "text": marker_text[index] if index < len(marker_text) else "",
            }

    return {
        "rows": rows,
        "bar_color": _static_trace_color(bar_traces[0], "#333333"),
        "marker_color": (
            _static_trace_color(marker_trace, RELATED_METRIC_MARKER_COLOR)
            if marker_trace is not None
            else RELATED_METRIC_MARKER_COLOR
        ),
        "markers_by_label": markers_by_label,
        "annotations_by_label": annotations_by_label,
        "title_lines": _static_title_lines(fig),
        "total_label": total_label,
    }


def _write_static_horizontal_bar_png(
    fig: Any,
    path: Path,
    width: int,
    height: int,
) -> str | None:
    """Write a deterministic PNG for simple horizontal bar-plus-marker figures."""

    payload = _static_horizontal_bar_payload(fig)
    if payload is None:
        return "Figure is not a simple horizontal bar chart."

    rows = list(reversed(payload["rows"]))
    width = max(int(width), 900)
    height = max(int(height), 560)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _static_font(12)
    total_value_font = _static_font(16, bold=True)
    small_font = _static_font(12)
    label_font = _static_font(13)
    value_font = _static_font(13)
    marker_font = _static_font(10, bold=True)
    segment_font = _static_font(10)

    left = 128
    right = 110
    top = 92
    bottom = 38
    plot_width = width - left - right
    plot_height = height - top - bottom
    row_height = plot_height / max(len(rows), 1)
    bar_height = min(30.0, max(9.0, row_height * 0.68))
    max_bar = max(float(row["value"]) for row in rows)
    if max_bar <= 0:
        return "Horizontal bar chart has no positive values."

    _draw_static_title_lines(
        draw,
        payload["title_lines"],
        x=left,
        y=24,
        line_height=18,
        font=title_font,
        max_lines=3,
    )
    total_label = payload.get("total_label")
    if total_label:
        total_lines = [line for line in str(total_label).splitlines() if line.strip()]
        for line_index, line in enumerate(total_lines[-2:]):
            draw.text(
                (width - right + 10, 35 + (line_index * 17)),
                line,
                fill="#2F3437",
                font=small_font if line_index == 0 else total_value_font,
            )

    markers_by_label = payload["markers_by_label"]
    max_marker = max(
        (float(marker["value"]) for marker in markers_by_label.values()),
        default=0.0,
    )
    marker_color = str(payload["marker_color"] or RELATED_METRIC_MARKER_COLOR)
    for index, row in enumerate(rows):
        y_center = top + (row_height * (index + 0.5))
        y0 = int(y_center - (bar_height / 2.0))
        y1 = int(y_center + (bar_height / 2.0))
        value = float(row["value"])
        x_position = float(left)
        segments = row.get("segments") or []
        for segment in segments:
            segment_value = float(segment["value"])
            segment_width = (segment_value / (max_bar * 1.08)) * plot_width
            x0 = int(x_position)
            x1 = int(x_position + segment_width)
            draw.rectangle((x0, y0, x1, y1), fill=str(segment["color"]))
            segment_share = segment_value / max(value, 1.0)
            segment_text = str(segment.get("text") or "")
            if len(segments) > 1 and segment_text and segment_share >= 0.08:
                segment_text = _static_ellipsize_preserve_suffix(
                    segment_text,
                    max(0.0, (x1 - x0) - 8),
                    segment_font,
                )
                text_box = draw.textbbox((0, 0), segment_text, font=segment_font)
                if segment_text and (text_box[2] - text_box[0]) <= (x1 - x0 - 4):
                    draw.text(
                        (
                            x0 + ((x1 - x0 - (text_box[2] - text_box[0])) / 2),
                            y_center - ((text_box[3] - text_box[1]) / 2),
                        ),
                        segment_text,
                        fill="white",
                        font=segment_font,
                    )
            x_position += segment_width
        x1 = int(x_position)

        label = str(row["label"])
        label_box = draw.textbbox((0, 0), label, font=label_font)
        draw.text(
            (left - 10 - (label_box[2] - label_box[0]), y_center - 8),
            label,
            fill="#2F3437",
            font=label_font,
        )

        value_text = (
            payload["annotations_by_label"].get(label)
            or str(row.get("text") or "")
            or _static_compact_number(value)
        )
        draw.text(
            (x1 + 10, y_center - 8),
            value_text,
            fill="#2F3437",
            font=value_font,
        )

        marker = markers_by_label.get(label)
        if marker is None or max_marker <= 0:
            continue
        marker_value = float(marker["value"])
        marker_x = int(left + ((marker_value / (max_marker * 1.08)) * plot_width))
        marker_text = str(marker.get("text") or _static_compact_number(marker_value))
        marker_box = draw.textbbox((0, 0), marker_text, font=marker_font)
        radius = max(
            RELATED_METRIC_MARKER_SIZE // 2,
            int(((marker_box[2] - marker_box[0]) / 2) + 2),
        )
        draw.ellipse(
            (
                marker_x - radius,
                int(y_center) - radius,
                marker_x + radius,
                int(y_center) + radius,
            ),
            fill=marker_color,
        )
        draw.text(
            (
                marker_x - ((marker_box[2] - marker_box[0]) / 2),
                y_center - ((marker_box[3] - marker_box[1]) / 2),
            ),
            marker_text,
            fill="white",
            font=marker_font,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return None


def _screenshot_plotly_html(
    html_path: Path, png_path: Path, width: int, height: int
) -> str | None:
    chrome = _find_headless_chrome()
    if chrome is None:
        return "Headless Chrome executable was not found."
    resolved_html_path = html_path.resolve()
    resolved_png_path = png_path.resolve()
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={resolved_png_path}",
        resolved_html_path.as_uri(),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    if result.returncode != 0:
        details = "\n".join(
            part for part in (result.stderr.strip(), result.stdout.strip()) if part
        )
        return details or f"Headless Chrome exited with status {result.returncode}."
    if not png_path.exists() or png_path.stat().st_size == 0:
        return "Headless Chrome did not write a PNG screenshot."
    return None


def _screenshot_plotly_html_with_playwright(
    html_path: Path, png_path: Path, width: int, height: int
) -> str | None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return f"Playwright is unavailable: {exc}"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            try:
                page = browser.new_page(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                )
                page.goto(
                    html_path.resolve().as_uri(), wait_until="load", timeout=30_000
                )
                page.wait_for_timeout(1_500)
                locator = page.locator(".plotly-graph-div").first
                if locator.count() > 0:
                    locator.screenshot(path=str(png_path), timeout=60_000)
                else:
                    page.screenshot(
                        path=str(png_path),
                        full_page=True,
                        timeout=60_000,
                    )
            finally:
                browser.close()
    except (OSError, RuntimeError, TimeoutError, PlaywrightError) as exc:
        return str(exc)
    if not png_path.exists() or png_path.stat().st_size == 0:
        return "Playwright did not write a PNG screenshot."
    return None


def _combined_screenshot_error(
    chrome_error: str | None,
    playwright_error: str | None,
) -> str | None:
    if chrome_error is None or playwright_error is None:
        return None
    return (
        f"Chrome screenshot failed: {chrome_error}; "
        f"Playwright screenshot failed: {playwright_error}"
    )


def _write_legacy_figure(fig: Any, path: Path) -> tuple[list[Path], dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    export_fig, normalization_audit = normalize_plotly_figure_for_static_export(fig)
    layout = getattr(export_fig, "layout", None)
    original_layout_width = int(getattr(layout, "width", 0) or 0)
    original_layout_height = int(getattr(layout, "height", 0) or 0)
    export_width, export_height = _legacy_export_size(export_fig, path.name)
    _preserve_legacy_single_panel_plot_width(
        export_fig, original_layout_width, export_width
    )
    export_fig.update_layout(
        width=export_width,
        height=export_height,
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            export_fig.write_image(
                str(path),
                format="png",
                width=export_width,
                height=export_height,
                scale=2,
            )
        stale_html_path = path.with_suffix(".html")
        if stale_html_path.exists():
            stale_html_path.unlink()
        return [path], {
            "artifact": path.name,
            "renderer": "legacy_plotly+kaleido",
            "plotly_export_error": None,
            "html_artifact": None,
            "screenshot_error": None,
            "export_width": export_width,
            "export_height": export_height,
            "legacy_layout_width": original_layout_width or None,
            "legacy_layout_height": original_layout_height or None,
            "figure_export_normalization": normalization_audit,
        }
    except (OSError, RuntimeError, ValueError) as exc:
        html_path = _write_plotly_html(export_fig, path, export_width, export_height)
        chrome_screenshot_error = _screenshot_plotly_html(
            html_path, path, export_width, export_height
        )
        playwright_screenshot_error = None
        if chrome_screenshot_error is not None:
            playwright_screenshot_error = _screenshot_plotly_html_with_playwright(
                html_path, path, export_width, export_height
            )
        screenshot_error = _combined_screenshot_error(
            chrome_screenshot_error,
            playwright_screenshot_error,
        )
        renderer = (
            "legacy_plotly+html_chrome_screenshot"
            if chrome_screenshot_error is None
            else (
                "legacy_plotly+html_playwright_screenshot"
                if playwright_screenshot_error is None
                else "legacy_plotly+html_only"
            )
        )
        paths = [html_path]
        if screenshot_error is None:
            paths.append(path)
        return paths, {
            "artifact": path.name if screenshot_error is None else html_path.name,
            "renderer": renderer,
            "plotly_export_error": str(exc),
            "html_artifact": html_path.name,
            "screenshot_error": screenshot_error,
            "chrome_screenshot_error": chrome_screenshot_error,
            "playwright_screenshot_error": playwright_screenshot_error,
            "static_fallback_policy": "disabled",
            "export_width": export_width,
            "export_height": export_height,
            "legacy_layout_width": original_layout_width or None,
            "legacy_layout_height": original_layout_height or None,
            "figure_export_normalization": normalization_audit,
        }


def _write_captured_figures(
    notifier: _LegacyCaptureNotifier,
    output_dir: Path,
    artifact_name: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    if not notifier.figures:
        return [], []
    paths: list[str] = []
    exports: list[dict[str, str | None]] = []
    for index, fig in enumerate(notifier.figures, start=1):
        path = output_dir / artifact_name
        if len(notifier.figures) > 1 and index > 1:
            path = path.with_name(f"{path.stem}_{index}{path.suffix}")
        export_fig, capture_normalization_audit = (
            normalize_plotly_figure_for_static_export(fig)
        )
        written_paths, export = _write_legacy_figure(export_fig, path)
        export["captured_figure_normalization"] = capture_normalization_audit
        paths.extend(str(written_path) for written_path in written_paths)
        exports.append(export)
    return paths, exports


def _collect_legacy_lazy_frame(value: Any) -> Any:
    """Materialize legacy Polars LazyFrames for helpers that expect DataFrames."""

    if not isinstance(value, pl.LazyFrame):
        return value
    try:
        return value.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return value.collect()


def _annotation_texts(figure: Any) -> list[str]:
    annotations = getattr(getattr(figure, "layout", None), "annotations", None) or []
    return [str(getattr(annotation, "text", "")) for annotation in annotations]


def _clear_total_column_bar_text(figures: list[Any], spec: dict[str, Any]) -> None:
    """Suppress internal bar labels for total-column charts."""

    if not spec.get("total_column_dimension"):
        return
    for figure in figures:
        for trace in _sequence(getattr(figure, "data", None)):
            if str(getattr(trace, "type", "") or "") != "bar":
                continue
            values = _sequence(getattr(trace, "text", None))
            if values:
                trace.text = [""] * len(values)
            trace.texttemplate = None


def _first_total_cagr_value(
    chart: dict[str, Any], names: dict[str, str]
) -> float | None:
    period_name = names["periodName"]
    candidates = [names["CXGRTotal"], names["CXGRData"]]
    for key in candidates:
        frame = chart.get(key)
        if frame is None:
            continue
        frame = _collect_legacy_lazy_frame(frame)
        if not isinstance(frame, pl.DataFrame) or frame.is_empty():
            continue
        columns = [column for column in frame.columns if column != period_name]
        for column in columns:
            value = frame.get_column(column).drop_nulls().first()
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    return None


def _apply_total_column_cagr_annotation(
    figures: list[Any],
    chart: dict[str, Any],
    names: dict[str, str],
    add_first_row_annotations: Callable[..., Any],
    growth_label: str | None = None,
) -> None:
    """Add the legacy CAGR header for total-only stacked-column figures."""

    if not figures or not chart.get(names["showCAGR"]):
        return
    if not chart.get(names["CXGRMetricName"]):
        return
    if names["CXGRTotal"] not in chart and names["CXGRData"] not in chart:
        return
    for key in (names["CXGRTotal"], names["CXGRData"], names["periodsMissing"]):
        if key in chart:
            chart[key] = _collect_legacy_lazy_frame(chart[key])
    total_cagr_value = _first_total_cagr_value(chart, names)
    if total_cagr_value is None:
        return
    chart[names["CXGRTotal"]] = pl.DataFrame({names["totalName"]: [total_cagr_value]})
    if growth_label:
        chart[names["CXGRMetricName"]] = growth_label
    for figure in figures:
        if any("CAGR" in text for text in _annotation_texts(figure)):
            continue
        add_first_row_annotations(figure, chart, 2, 1, None, None)


def _is_percentage_label(text: str) -> bool:
    normalized = re.sub(r"<[^>]+>", " ", str(text or ""))
    return bool("%" in normalized and re.search(r"[+-]?\d+(?:\.\d+)?\s*%", normalized))


def _is_standalone_growth_annotation(text: str) -> bool:
    normalized = re.sub(r"<[^>]+>", " ", str(text or "")).strip()
    if not _is_percentage_label(normalized):
        return False
    return "CAGR" not in normalized.upper()


def _is_right_lane_growth_annotation(annotation: Any) -> bool:
    """Return whether a percent annotation is a right-side item CAGR label."""

    xref = str(getattr(annotation, "xref", "") or "")
    xanchor = str(getattr(annotation, "xanchor", "") or "").lower()
    xshift = _float_or_none(getattr(annotation, "xshift", None)) or 0.0
    return xref.startswith("x") and xanchor == "left" and xshift >= 40


def _right_lane_growth_reference_annotation(figure: Any) -> Any | None:
    """Return a representative right-side percentage annotation."""

    annotations = getattr(getattr(figure, "layout", None), "annotations", None) or []
    for annotation in annotations:
        if _is_right_lane_growth_annotation(annotation) and _is_percentage_label(
            str(getattr(annotation, "text", "") or "")
        ):
            return annotation
    return None


def _numeric_label_decimal_places(value: Any) -> int | None:
    text = re.sub(r"<[^>]+>", " ", str(value or "")).strip()
    if not text or "%" in text:
        return None
    normalized = re.sub(r"\s+", "", text).replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalized):
        return None
    if "." not in normalized:
        return 0
    return len(normalized.rsplit(".", 1)[1])


def _stacked_total_label_decimal_places(figure: Any) -> int | None:
    decimals = [
        decimal_places
        for annotation in _sequence(getattr(figure.layout, "annotations", None))
        if (
            decimal_places := _numeric_label_decimal_places(
                getattr(annotation, "text", "")
            )
        )
        is not None
    ]
    return max(decimals) if decimals else None


def _format_decimal_label(value: Decimal, decimal_places: int) -> str:
    if decimal_places <= 0:
        return str(int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    quantum = Decimal("1").scaleb(-decimal_places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded:.{decimal_places}f}"


def _format_stacked_value_label_like_total(
    value: Any, total_decimal_places: int | None = None
) -> Any:
    text = str(value or "").strip()
    if not text or _is_percentage_label(text):
        return value
    normalized = text.replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalized):
        return value
    try:
        numeric_value = Decimal(normalized)
    except InvalidOperation:
        return value
    if total_decimal_places is not None:
        return _format_decimal_label(numeric_value, total_decimal_places)
    if numeric_value == numeric_value.to_integral_value() and "." not in normalized:
        return str(int(numeric_value))
    return _format_decimal_label(numeric_value, 1)


def _force_horizontal_stacked_value_labels(figure: Any) -> None:
    for trace in _sequence(getattr(figure, "data", None)):
        if str(getattr(trace, "type", "") or "") not in {"bar", ""}:
            continue
        if str(getattr(trace, "orientation", "") or "").lower() == "h":
            continue
        trace.textangle = 0


def _is_zero_rounded_value_label(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(re.fullmatch(r"[+-]?0(?:\.0+)?", text))


def _stacked_label_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).replace("<BR>", "<br>")


def _has_single_active_trace(figure: Any) -> bool:
    traces = [
        trace
        for trace in _sequence(getattr(figure, "data", None))
        if str(getattr(trace, "type", "") or "") in {"bar", ""}
    ]
    if len(traces) != 1:
        return False
    return str(getattr(traces[0], "name", "") or "").strip().lower() == "active"


def _blank_trace_text(trace: Any) -> list[str]:
    value_count = len(_sequence(getattr(trace, "text", None)))
    if value_count == 0:
        value_count = len(_sequence(getattr(trace, "y", None)))
    if value_count == 0:
        value_count = len(_sequence(getattr(trace, "x", None)))
    return [""] * value_count


def _column_position_key(trace: Any, index: int) -> tuple[str, str]:
    x_values = _sequence(getattr(trace, "x", None))
    if index < len(x_values):
        value = x_values[index]
    else:
        value = index
    try:
        hash(value)
        key = repr(value)
    except TypeError:
        key = repr(value)
    return (_axis_name(trace, "x"), key)


def _suppress_single_visible_column_segment_labels(figure: Any) -> None:
    """Blank internal labels where a column has only one visible segment."""

    entries_by_column: dict[tuple[str, str], list[tuple[Any, int]]] = {}
    for trace in _sequence(getattr(figure, "data", None)):
        if str(getattr(trace, "type", "") or "") not in {"bar", ""}:
            continue
        if str(getattr(trace, "orientation", "") or "").lower() == "h":
            continue
        text_values = _sequence(getattr(trace, "text", None))
        y_values = _sequence(getattr(trace, "y", None))
        for index, value in enumerate(text_values):
            if not str(value or "").strip():
                continue
            y_value = _float_or_none(y_values[index] if index < len(y_values) else None)
            if y_value is None or y_value == 0:
                continue
            key = _column_position_key(trace, index)
            entries_by_column.setdefault(key, []).append((trace, index))

    for entries in entries_by_column.values():
        if len(entries) != 1:
            continue
        trace, index = entries[0]
        text_values = _sequence(getattr(trace, "text", None))
        if index >= len(text_values):
            continue
        text_values[index] = ""
        trace.text = text_values


def _suppress_stacked_percentage_labels(
    figures: list[Any],
    spec: dict[str, Any],
) -> None:
    """Remove legacy segment-growth labels from stacked composition charts."""

    suppress_percentages = bool(spec.get("suppress_stacked_percentage_annotations"))
    format_values = bool(spec.get("format_stacked_value_labels_like_totals"))
    suppress_single_active = bool(spec.get("suppress_single_active_value_label"))
    suppress_zero_rounded = bool(spec.get("suppress_zero_rounded_stacked_labels"))
    if not (
        suppress_percentages
        or format_values
        or suppress_single_active
        or suppress_zero_rounded
    ):
        return
    for figure in figures:
        annotations = []
        for annotation in _sequence(getattr(figure.layout, "annotations", None)):
            text = str(getattr(annotation, "text", "") or "")
            if (
                suppress_percentages
                and _is_standalone_growth_annotation(text)
                and not _is_right_lane_growth_annotation(annotation)
            ):
                continue
            annotations.append(annotation)
        figure.layout.annotations = tuple(annotations)

        single_active_trace = suppress_single_active and _has_single_active_trace(
            figure
        )
        total_decimal_places = (
            _stacked_total_label_decimal_places(figure) if format_values else None
        )
        suppressed_trace_labels: set[str] = set()
        for trace in _sequence(getattr(figure, "data", None)):
            text_values = _sequence(getattr(trace, "text", None))
            if single_active_trace:
                trace.text = _blank_trace_text(trace)
                trace.texttemplate = None
                continue
            if not text_values:
                continue
            cleaned_values = []
            for value in text_values:
                if suppress_percentages and _is_percentage_label(str(value)):
                    cleaned_values.append("")
                elif format_values:
                    formatted_value = _format_stacked_value_label_like_total(
                        value,
                        total_decimal_places,
                    )
                    if suppress_zero_rounded and _is_zero_rounded_value_label(
                        formatted_value
                    ):
                        cleaned_values.append("")
                    else:
                        cleaned_values.append(formatted_value)
                else:
                    cleaned_values.append(value)
            if cleaned_values != text_values:
                trace.text = cleaned_values
            if (
                suppress_zero_rounded
                and cleaned_values
                and all(not str(value or "").strip() for value in cleaned_values)
            ):
                trace_label = _stacked_label_key(getattr(trace, "name", ""))
                if trace_label != "Active":
                    suppressed_trace_labels.add(trace_label)
            text_template = str(getattr(trace, "texttemplate", "") or "")
            if suppress_percentages and _is_percentage_label(text_template):
                trace.texttemplate = None
        if suppressed_trace_labels:
            figure.layout.annotations = tuple(
                annotation
                for annotation in _sequence(getattr(figure.layout, "annotations", None))
                if _stacked_label_key(getattr(annotation, "text", ""))
                not in suppressed_trace_labels
            )
        if format_values:
            _suppress_single_visible_column_segment_labels(figure)
            _force_horizontal_stacked_value_labels(figure)


def _apply_display_dimension_label(
    figures: list[Any],
    spec: dict[str, Any],
) -> None:
    """Replace technical cohort column names in captured chart titles."""

    display_label = str(spec.get("display_dimension_label") or "").strip()
    source_label = str(
        spec.get("cohort_dimension") or spec.get("y_dimension") or ""
    ).strip()
    if not display_label or not source_label:
        return
    for figure in figures:
        for annotation in _sequence(getattr(figure.layout, "annotations", None)):
            text = str(getattr(annotation, "text", "") or "")
            if not text:
                continue
            annotation.text = text.replace(
                f" by {source_label}",
                f" by {display_label}",
            )


def _unwrap_cohort_label_annotations(
    figures: list[Any],
    spec: dict[str, Any],
) -> None:
    """Keep cohort item labels on one line after legacy wrapping."""

    if not spec.get("cohort_kind"):
        return
    label_prefixes = ("Since ", "Lost after ", "Lost before ", "Before ")
    for figure in figures:
        for annotation in _sequence(getattr(figure.layout, "annotations", None)):
            text = str(getattr(annotation, "text", "") or "")
            normalized = re.sub(
                r"\s+",
                " ",
                text.replace("<BR>", " ").replace("<br>", " "),
            ).strip()
            if any(normalized.startswith(prefix) for prefix in label_prefixes):
                annotation.text = normalized
                if hasattr(annotation, "hovertext"):
                    annotation.hovertext = normalized


def _spread_cohort_label_annotations(
    figures: list[Any],
    spec: dict[str, Any],
) -> None:
    """Separate visible cohort item labels that sit on tiny adjacent slices."""

    if not spec.get("cohort_kind"):
        return
    label_prefixes = ("Since ", "Lost after ", "Lost before ", "Before ")
    for figure in figures:
        visible_labels: list[Any] = []
        for annotation in _sequence(getattr(figure.layout, "annotations", None)):
            text = str(getattr(annotation, "text", "") or "").strip()
            if not any(text.startswith(prefix) for prefix in label_prefixes):
                continue
            if _float_or_none(getattr(annotation, "y", None)) is None:
                continue
            visible_labels.append(annotation)
        if len(visible_labels) < 2:
            continue

        trace_values: list[float] = []
        for trace in _sequence(getattr(figure, "data", None)):
            trace_values.extend(
                _numeric_trace_values(_sequence(getattr(trace, "y", None)))
            )
        value_span = max(trace_values) - min(trace_values) if trace_values else 0.0
        min_gap = max(value_span * 0.045, 0.03)

        groups: dict[tuple[str, str, float | None], list[Any]] = {}
        for annotation in visible_labels:
            x_value = _float_or_none(getattr(annotation, "x", None))
            key = (
                str(getattr(annotation, "xref", "") or ""),
                str(getattr(annotation, "yref", "") or ""),
                round(x_value, 3) if x_value is not None else None,
            )
            groups.setdefault(key, []).append(annotation)

        for annotations in groups.values():
            if len(annotations) < 2:
                continue
            annotations.sort(
                key=lambda item: _float_or_none(getattr(item, "y", None)) or 0.0
            )
            previous_y = _float_or_none(getattr(annotations[0], "y", None))
            if previous_y is None:
                continue
            for annotation in annotations[1:]:
                current_y = _float_or_none(getattr(annotation, "y", None))
                if current_y is None:
                    continue
                adjusted_y = max(current_y, previous_y + min_gap)
                if adjusted_y != current_y:
                    annotation.y = adjusted_y
                previous_y = adjusted_y


def _total_cagr_from_period_totals(
    period_totals: dict[str, float],
    selected_periods: Sequence[str],
) -> float | None:
    periods = [
        period_text
        for period in selected_periods
        if (period_text := str(period).strip())
    ]
    periods = list(dict.fromkeys(periods))
    if len(periods) < 2:
        return None
    first_total = period_totals.get(periods[0])
    last_total = period_totals.get(periods[-1])
    if first_total is None or last_total is None or first_total <= 0 or last_total <= 0:
        return None
    elapsed_periods = len(periods) - 1
    try:
        return ((last_total / first_total) ** (1 / elapsed_periods) - 1) * 100
    except (OverflowError, ZeroDivisionError, ValueError):
        return None


def _apply_stacked_total_cagr_annotation(
    figures: list[Any],
    spec: dict[str, Any],
    period_totals: dict[str, float],
    selected_periods: Sequence[str],
) -> None:
    """Add a single total CAGR header for multi-period stacked composition charts."""

    if not spec.get("show_total_cagr"):
        return
    total_cagr = _total_cagr_from_period_totals(period_totals, selected_periods)
    if total_cagr is None:
        return
    text = f"CAGR<br>{total_cagr:+.1f}%"
    for figure in figures:
        if any("CAGR" in existing for existing in _annotation_texts(figure)):
            continue
        reference = _right_lane_growth_reference_annotation(figure)
        if reference is not None:
            ref_font = getattr(reference, "font", None)
            ref_font_size = _float_or_none(getattr(ref_font, "size", None))
            annotation_kwargs = {
                "x": getattr(reference, "x", 1.0),
                "xref": getattr(reference, "xref", "x"),
                "xanchor": getattr(reference, "xanchor", "left"),
                "xshift": getattr(reference, "xshift", 0),
                "align": getattr(reference, "align", "left") or "left",
                "font": {
                    "size": int(ref_font_size) if ref_font_size else 12,
                    "color": "#111827",
                },
            }
        else:
            annotation_kwargs = {
                "x": 1.0,
                "xref": "paper",
                "xanchor": "right",
                "align": "right",
                "font": {"size": 12, "color": "#111827"},
            }
        figure.add_annotation(
            text=text,
            y=1.03,
            yref="paper",
            yanchor="bottom",
            showarrow=False,
            **annotation_kwargs,
        )
        current_margin = figure.layout.margin or {}
        margin_dict = (
            current_margin.to_plotly_json()
            if hasattr(current_margin, "to_plotly_json")
            else {}
        )
        figure.update_layout(
            margin={
                **margin_dict,
                "t": max(int(getattr(current_margin, "t", 0) or 0), 90),
            }
        )


def write_legacy_mix_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    spec: dict[str, Any],
    prepared_data_cache: LegacyPreparedDataCache | None = None,
    *,
    render: bool = True,
) -> LegacyMixChartExport:
    """Run one vendored legacy chart attempt and optionally export captured figures."""

    _ensure_legacy_import_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from modules.charting import draw_charts_utils, draw_width_and_stacked_plots
        from modules.charting import draw_timeline as draw_timeline_module
        from modules.charting import plot_charts as plot_charts_module
        from modules.charting import prepare_charts as prepare_charts_module
        from modules.charting.chart_primitives import get_color_dictionary
        from modules.charting.run_charting import run_charting
        from modules.chart_harness import apply_legacy_filter_title_metadata
        from modules.data import misc_charts_data_prep
        from modules.data import multidimensional_charts_prep as stacked_column_prep
        from modules.utilities.config import get_naming_params

        names = get_naming_params()
        cache_start = (
            prepared_data_cache.snapshot() if prepared_data_cache is not None else None
        )

        def _cache_audit() -> dict[str, Any]:
            if prepared_data_cache is None or cache_start is None:
                return {"prepared_data_cache": {"enabled": False}}
            return prepared_data_cache.audit_delta(cache_start)

        metric = str(recipe["mappings"]["amount_column"])
        currency = str((recipe.get("options") or {}).get("currency") or "EUR")
        chart = _legacy_chart_dict(names, spec, metric=metric, currency=currency)
        chart = apply_legacy_filter_title_metadata(chart, names, recipe)
        selected_periods = [str(item) for item in chart[names["selectedPeriods"]]]
        chart_input, selected_periods, chart, period_adapter_audit = (
            _apply_legacy_period_grain_selection(
                canonical,
                names,
                chart,
                spec,
                recipe,
                selected_periods,
            )
        )
        spec = {
            **spec,
            "selected_periods": selected_periods,
            "period_adapter": period_adapter_audit,
            "period_comparison_mode": period_adapter_audit.get("period_comparison_mode")
            or spec.get("period_comparison_mode"),
        }
        total_column_dimension = spec.get("total_column_dimension")
        if total_column_dimension:
            total_column_dimension = str(total_column_dimension)
            if total_column_dimension not in chart_input.columns:
                chart_input = chart_input.with_columns(
                    pl.lit(str(spec.get("total_column_label") or "Total")).alias(
                        total_column_dimension
                    )
                )
        raw_periods = _period_values_from_frame(chart_input, CANONICAL_PERIOD)
        cohort_param = _legacy_param_dict(
            names,
            total=0.0,
            selected_periods=raw_periods or selected_periods,
            period_totals={},
            columns=chart_input.columns,
            date_period_choice=chart.get(names["datePeriodName"]),
        )
        chart_input = _apply_legacy_cohort_columns(
            chart_input, names, cohort_param, chart, spec
        )
        chart_input = _apply_cohort_period_bucket(chart_input, spec)
        if selected_periods:
            selected_chart_input = chart_input.filter(
                pl.col(CANONICAL_PERIOD).cast(pl.Utf8).is_in(selected_periods)
            )
            if not selected_chart_input.is_empty():
                chart_input = selected_chart_input
        if spec.get("synthesis_plot") and selected_periods:
            current_period = selected_periods[-1]
            filtered = chart_input.filter(
                pl.col(CANONICAL_PERIOD).cast(pl.Utf8) == current_period
            )
            if not filtered.is_empty():
                chart_input = filtered
        parameter_frame = chart_input
        if selected_periods:
            selected_frame = chart_input.filter(
                pl.col(CANONICAL_PERIOD).cast(pl.Utf8).is_in(selected_periods)
            )
            if not selected_frame.is_empty():
                parameter_frame = selected_frame
        period_totals = {
            str(row[CANONICAL_PERIOD]): float(row[metric] or 0.0)
            for row in parameter_frame.group_by(CANONICAL_PERIOD)
            .agg(pl.col(metric).sum().alias(metric))
            .iter_rows(named=True)
        }
        total = (
            period_totals.get(selected_periods[-1], 0.0) if selected_periods else 0.0
        )
        least_recent_date, most_recent_date = _canonical_date_bounds(parameter_frame)
        param = _legacy_param_dict(
            names,
            total=total,
            selected_periods=selected_periods,
            period_totals=period_totals,
            columns=chart_input.columns,
            least_recent_date=least_recent_date,
            most_recent_date=most_recent_date,
            date_period_choice=chart.get(names["datePeriodName"]),
        )
        df_dict = _legacy_df_dict(names, chart_input)
        dimensions = _legacy_index_dimensions(recipe, spec)
        value_cols = list(
            dict.fromkeys(
                str(item)
                for item in spec.get("value_cols") or chart[names["metricsToPlot"]]
            )
        )
        captured_chart_calls: list[dict[str, Any]] = []
        source_functions = _legacy_source_functions(spec)
        uniform_synthesis_palette = bool(spec.get("synthesis_uniform_palette"))
        palette_policy = (
            "uniform_rank_palette"
            if uniform_synthesis_palette
            else "legacy_dimension_shifted_palette"
        )
        with _capture_legacy_ui() as notifier:
            draw_width_and_stacked_plots.ui = notifier
            draw_width_and_stacked_plots.st = notifier
            draw_charts_utils.st = notifier
            original_plot_charts_setup = (
                plot_charts_module.set_up_tab_for_show_or_download_chart
            )
            original_draw_width_setup = (
                draw_width_and_stacked_plots.set_up_tab_for_show_or_download_chart
            )
            original_draw_timeline_setup = (
                draw_timeline_module.set_up_tab_for_show_or_download_chart
            )
            original_modify_color_array = stacked_column_prep.modify_color_array
            original_plot_mekko_group = (
                plot_charts_module.group_by_dataset_for_marimekko_and_barmekko
            )
            original_prepare_mekko_group = (
                prepare_charts_module.group_by_dataset_for_marimekko_and_barmekko
            )
            original_plot_stacked_bar_group = (
                plot_charts_module.group_by_dataset_for_stacked_bar
            )
            original_prepare_stacked_bar_group = (
                prepare_charts_module.group_by_dataset_for_stacked_bar
            )
            original_plot_resample_dates = plot_charts_module.resample_dates
            original_prepare_resample_dates = prepare_charts_module.resample_dates
            original_plot_show_only_largest = plot_charts_module.show_only_largest
            original_plot_prepare_pareto = plot_charts_module.prepare_data_for_pareto
            original_plot_rank_others_as_last = plot_charts_module.rank_others_as_last
            original_plot_stacked_bar_width_plot = (
                plot_charts_module.stacked_bar_width_plot
            )
            original_plot_calculate_data_column_metrics = (
                plot_charts_module.calculate_metrics_for_data_column
            )
            original_prepare_stacked_bar_small_multiples = (
                stacked_column_prep.prepare_small_multiples_dataframe_for_stacked_bar
            )
            original_draw_prepare_stacked_bar_small_multiples = (
                draw_width_and_stacked_plots.prepare_small_multiples_dataframe_for_stacked_bar
            )
            original_plot_stacked_pareto_title = (
                plot_charts_module.make_stacked_pareto_and_pareto_chart_title
            )
            original_plot_transpose_chart_frame = (
                plot_charts_module.transpose_chart_frame
            )
            original_plot_make_pareto_classes = (
                plot_charts_module.make_df_for_pareto_classes
            )
            original_plot_make_pareto_items = (
                plot_charts_module.make_df_for_pareto_items
            )
            original_misc_prepare_pareto = misc_charts_data_prep.prepare_data_for_pareto
            original_misc_color_pareto_classes = (
                misc_charts_data_prep.color_pareto_classes
            )
            if uniform_synthesis_palette:
                stacked_column_prep.modify_color_array = (
                    lambda hex_colors, _counter: hex_colors
                )

            def _cached_mekko_group(
                df_copy: pl.DataFrame | pl.LazyFrame,
                column: str,
                small_multiples_column_array: list[str],
                grouped_value_cols: list[str],
                chart_dict: dict[str, Any],
            ) -> pl.DataFrame | pl.LazyFrame:
                if prepared_data_cache is None:
                    return original_prepare_mekko_group(
                        df_copy,
                        column,
                        small_multiples_column_array,
                        grouped_value_cols,
                        chart_dict,
                    )
                return prepared_data_cache.get_mekko_grouped_frame(
                    names,
                    column,
                    small_multiples_column_array,
                    grouped_value_cols,
                    chart_dict,
                    original_prepare_mekko_group,
                    df_copy,
                    dimensions,
                )

            def _cached_stacked_bar_group(
                df_copy: pl.DataFrame | pl.LazyFrame,
                column: str,
                small_multiples_column_array: list[str],
                grouped_value_cols: list[str],
                chart_dict: dict[str, Any],
            ) -> tuple[pl.LazyFrame, list[str]]:
                if prepared_data_cache is None:
                    return original_prepare_stacked_bar_group(
                        df_copy,
                        column,
                        small_multiples_column_array,
                        grouped_value_cols,
                        chart_dict,
                    )

                def _build_stacked_bar_frame(
                    source_frame: pl.DataFrame | pl.LazyFrame,
                    source_column: str,
                    source_small_multiples: list[str],
                    source_value_cols: list[str],
                    source_chart_dict: dict[str, Any],
                ) -> pl.LazyFrame:
                    frame, _group_cols = original_prepare_stacked_bar_group(
                        source_frame,
                        source_column,
                        source_small_multiples,
                        source_value_cols,
                        source_chart_dict,
                    )
                    return frame

                grouped = prepared_data_cache.get_mekko_grouped_frame(
                    names,
                    column,
                    small_multiples_column_array,
                    grouped_value_cols,
                    chart_dict,
                    _build_stacked_bar_frame,
                    df_copy,
                    dimensions,
                )
                group_cols, _ = prepared_data_cache._target_mekko_columns(
                    names,
                    column,
                    small_multiples_column_array,
                    grouped_value_cols,
                    chart_dict,
                    prepared_data_cache._columns(df_copy),
                )
                return grouped, group_cols

            def _cached_resample_dates(
                df_lazy: pl.LazyFrame,
                x_column: str,
                column: str,
                resample_value_cols: list[str],
                chart_dict: dict[str, Any],
                agg: str,
                param_dict: dict[str, Any],
            ) -> pl.LazyFrame:
                if prepared_data_cache is None:
                    return original_prepare_resample_dates(
                        df_lazy,
                        x_column,
                        column,
                        resample_value_cols,
                        chart_dict,
                        agg,
                        param_dict,
                    )
                cache_key = (
                    prepared_data_cache._frame_signature(df_lazy),
                    chart_dict.get(names["chosenChart"]),
                    x_column,
                    column,
                    tuple(resample_value_cols),
                    agg,
                    chart_dict.get(names["resampleDates"]),
                    chart_dict.get(names["compareScenariosOrPeriods"]),
                )
                return prepared_data_cache.get_lazy_stage_frame(
                    "resample_dates",
                    cache_key,
                    lambda: original_prepare_resample_dates(
                        df_lazy,
                        x_column,
                        column,
                        resample_value_cols,
                        chart_dict,
                        agg,
                        param_dict,
                    ),
                )

            def _cached_show_only_largest(
                df_copy: pl.DataFrame | pl.LazyFrame,
                column: str,
                second_column: str | None,
                time_column: str,
                top_value_cols: list[str],
                chart_dict: dict[str, Any],
                param_dict: dict[str, Any],
                key: str,
            ) -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
                if prepared_data_cache is None:
                    return original_plot_show_only_largest(
                        df_copy,
                        column,
                        second_column,
                        time_column,
                        top_value_cols,
                        chart_dict,
                        param_dict,
                        key,
                    )
                return prepared_data_cache.get_show_only_largest(
                    names,
                    original_plot_show_only_largest,
                    df_copy,
                    column,
                    second_column,
                    time_column,
                    top_value_cols,
                    chart_dict,
                    param_dict,
                    key,
                )

            def _cached_prepare_pareto(
                df_copy: pl.DataFrame | pl.LazyFrame,
                period: str,
                pareto_metric: str,
                chart_dict: dict[str, Any],
                param_dict: dict[str, Any],
                color_list_dict: dict[str, Any],
                class_color_dict: dict[str, Any],
                count: int,
            ) -> tuple[pl.LazyFrame, list[Any], dict[str, Any], str, str]:
                if prepared_data_cache is None:
                    result = original_misc_prepare_pareto(
                        df_copy,
                        period,
                        pareto_metric,
                        chart_dict,
                        param_dict,
                        color_list_dict,
                        class_color_dict,
                        count,
                    )
                else:
                    result = prepared_data_cache.get_pareto_prepared(
                        names,
                        original_misc_prepare_pareto,
                        df_copy,
                        period,
                        pareto_metric,
                        chart_dict,
                        param_dict,
                        color_list_dict,
                        class_color_dict,
                        count,
                    )
                (
                    prepared_frame,
                    color_list,
                    prepared_class_color_dict,
                    prepared_metric,
                    ratio_name,
                ) = result
                class_name = names["className"]
                if (
                    spec.get("stacked_pareto_mode") == "abc_classes"
                    and class_name not in prepared_class_color_dict
                    and prepared_metric in prepared_class_color_dict
                ):
                    prepared_class_color_dict[class_name] = prepared_class_color_dict[
                        prepared_metric
                    ]
                return (
                    prepared_frame,
                    color_list,
                    prepared_class_color_dict,
                    prepared_metric,
                    ratio_name,
                )

            def _safe_make_df_for_pareto_classes(
                df: pl.DataFrame | pl.LazyFrame,
                df_counts: pl.DataFrame | pl.LazyFrame,
            ) -> tuple[pl.LazyFrame, list[str], str]:
                class_name = names["className"]
                count_columns = LegacyPreparedDataCache._columns(df_counts)
                if class_name in count_columns:
                    return original_plot_make_pareto_classes(df, df_counts)
                prepared_columns = LegacyPreparedDataCache._columns(df)
                if class_name not in prepared_columns:
                    return original_plot_make_pareto_classes(df, df_counts)
                count_value_columns = [
                    column for column in count_columns if column != class_name
                ]
                if not count_value_columns:
                    return original_plot_make_pareto_classes(df, df_counts)
                count_column = count_value_columns[-1]
                df_lazy = df.lazy() if isinstance(df, pl.DataFrame) else df
                return (
                    df_lazy.with_columns(pl.lit(1).alias(count_column)),
                    [class_name],
                    class_name,
                )

            def _safe_make_df_for_pareto_items(
                df: pl.DataFrame | pl.LazyFrame,
                df_counts: pl.DataFrame | pl.LazyFrame,
                count_name: str,
                chart_dict: dict[str, Any],
            ) -> tuple[pl.LazyFrame, list[str], str]:
                if spec.get("plotter") != "plot_stacked_pareto_chart":
                    return original_plot_make_pareto_items(
                        df, df_counts, count_name, chart_dict
                    )
                aggregate_dimension = chart_dict.get(names["aggregateUniquesDimension"])
                if not aggregate_dimension:
                    return original_plot_make_pareto_items(
                        df, df_counts, count_name, chart_dict
                    )
                item_frame = LegacyPreparedDataCache._collect_frame(df)
                count_frame = LegacyPreparedDataCache._collect_frame(df_counts)
                item_columns = LegacyPreparedDataCache._columns(item_frame)
                count_columns = LegacyPreparedDataCache._columns(count_frame)
                if (
                    aggregate_dimension not in item_columns
                    or aggregate_dimension not in count_columns
                    or count_name not in count_columns
                ):
                    return original_plot_make_pareto_items(
                        item_frame, count_frame, count_name, chart_dict
                    )
                displayed_items = (
                    item_frame.get_column(aggregate_dimension).cast(pl.Utf8).to_list()
                )
                aggregate_prefix = str(names["aggregateOtherItemsName"])
                other_items = [
                    item
                    for item in displayed_items
                    if str(item).startswith(aggregate_prefix)
                ]
                counts_for_join = count_frame.select([aggregate_dimension, count_name])
                if other_items:
                    other_item = other_items[0]
                    top_items = [item for item in displayed_items if item != other_item]
                    other_count = (
                        counts_for_join.filter(
                            ~pl.col(aggregate_dimension).is_in(top_items)
                        )
                        .select(pl.col(count_name).sum())
                        .item()
                    )
                    counts_for_join = pl.concat(
                        [
                            counts_for_join.filter(
                                pl.col(aggregate_dimension).is_in(top_items)
                            ),
                            pl.DataFrame(
                                {
                                    aggregate_dimension: pl.Series(
                                        aggregate_dimension,
                                        [other_item],
                                        dtype=count_frame.schema[aggregate_dimension],
                                    ),
                                    count_name: pl.Series(
                                        count_name,
                                        [other_count],
                                        dtype=count_frame.schema[count_name],
                                    ),
                                }
                            ),
                        ],
                        how="vertical",
                    )
                return (
                    item_frame.join(
                        counts_for_join, on=aggregate_dimension, how="left"
                    ).lazy(),
                    [str(aggregate_dimension)],
                    str(aggregate_dimension),
                )

            def _ordered_stacked_pareto_transpose(
                df: pl.DataFrame | pl.LazyFrame,
                *,
                header_name: str,
                column_names: str | None = None,
                include_header: bool = True,
            ) -> pl.LazyFrame:
                if (
                    spec.get("plotter") != "plot_stacked_pareto_chart"
                    or include_header
                    or not column_names
                ):
                    return original_plot_transpose_chart_frame(
                        df,
                        header_name=header_name,
                        column_names=column_names,
                        include_header=include_header,
                    )
                frame = LegacyPreparedDataCache._collect_frame(df)
                if column_names not in frame.columns:
                    return original_plot_transpose_chart_frame(
                        frame,
                        header_name=header_name,
                        column_names=column_names,
                        include_header=include_header,
                    )
                metric_marker = STACKED_PARETO_METRIC_LABEL_COLUMN
                transposed = frame.transpose(
                    include_header=True,
                    header_name=metric_marker,
                    column_names=column_names,
                )
                metric_order = _stacked_pareto_metric_order(chart, names)
                order_frame = pl.DataFrame(
                    {
                        metric_marker: metric_order,
                        "__metric_order": list(range(len(metric_order))),
                    }
                )
                ordered = (
                    transposed.join(order_frame, on=metric_marker, how="left")
                    .with_columns(pl.col("__metric_order").fill_null(9999))
                    .sort("__metric_order")
                    .drop("__metric_order")
                )
                columns = LegacyPreparedDataCache._columns(ordered)
                class_order = [
                    names["aClassName"],
                    names["bClassName"],
                    names["cClassName"],
                    names["negativeClassName"],
                    names["lossClassName"],
                ]
                ordered_columns = [metric_marker]
                ordered_columns.extend(
                    column for column in class_order if column in columns
                )
                ordered_columns.extend(
                    column
                    for column in columns
                    if column not in {*ordered_columns, metric_marker}
                )
                selected = ordered.select(ordered_columns)
                if isinstance(df, pl.LazyFrame):
                    return selected.lazy()
                return selected

            def _safe_calculate_metrics_for_data_column(
                df: pl.DataFrame | pl.LazyFrame,
                chart_dict: dict[str, Any],
                sum_cols_array: list[str],
                count_name: str,
            ) -> tuple[pl.DataFrame, dict[str, Any], list[str]]:
                if spec.get("plotter") == "plot_stacked_pareto_chart" and isinstance(
                    df, pl.LazyFrame
                ):
                    df = LegacyPreparedDataCache._collect_frame(df)
                return original_plot_calculate_data_column_metrics(
                    df, chart_dict, sum_cols_array, count_name
                )

            def _stacked_pareto_total_labels(
                df: pl.DataFrame | pl.LazyFrame,
                chart_dict: dict[str, Any],
            ) -> list[str]:
                frame = LegacyPreparedDataCache._collect_frame(df)
                columns = LegacyPreparedDataCache._columns(frame)
                marker = STACKED_PARETO_METRIC_LABEL_COLUMN
                if marker not in columns:
                    return []
                metric_names = [
                    str(item) for item in chart_dict[names["metricsToPlot"]]
                ]
                count_by_column = chart_dict.get(names["countByColumn"]) or (
                    f"{names['countName']} {chart_dict.get(names['countColumn'])}"
                )
                total_source = frame
                if metric_names:
                    metric_total_source = frame.filter(
                        pl.col(marker) == metric_names[0]
                    )
                    if not metric_total_source.is_empty():
                        total_source = metric_total_source
                metric_total_columns = {metric: metric for metric in metric_names[1:]}
                if metric_names:
                    metric_total_columns[metric_names[0]] = names["valueName"]
                metric_total_columns[str(count_by_column)] = str(count_by_column)
                labels: list[str] = []
                for metric_label in [*metric_names, str(count_by_column)]:
                    total_column = metric_total_columns.get(metric_label)
                    if not total_column or total_column not in columns:
                        labels.append("")
                        continue
                    if total_source.is_empty():
                        labels.append("")
                        continue
                    labels.append(
                        _format_stacked_pareto_total_label(
                            total_source.get_column(total_column)[0],
                            metric_label,
                            chart_dict,
                            names,
                            str(count_by_column),
                        )
                    )
                return labels

            def _replace_stacked_pareto_total_annotations(
                figure: Any,
                labels: list[str],
            ) -> Any:
                if not labels or not getattr(figure.layout, "annotations", None):
                    return figure
                candidates = []
                for annotation in figure.layout.annotations:
                    try:
                        x_value = float(annotation.x)
                    except (TypeError, ValueError):
                        continue
                    if (
                        getattr(annotation, "xref", None) == "x"
                        and getattr(annotation, "yref", None) == "paper"
                        and abs(float(getattr(annotation, "y", 0) or 0) - 1.0) < 1e-9
                        and not bool(getattr(annotation, "showarrow", False))
                        and x_value >= 0
                    ):
                        candidates.append(annotation)
                candidates = sorted(
                    candidates, key=lambda annotation: float(annotation.x)
                )
                positions = _stacked_pareto_total_x_positions(
                    figure,
                    min(len(candidates), len(labels)),
                )
                for index, (annotation, label) in enumerate(zip(candidates, labels)):
                    annotation.x = positions[index]
                    if label:
                        annotation.text = label
                    annotation.xanchor = "center"
                    annotation.align = "center"
                return figure

            def _stacked_pareto_width_plot(
                df: pl.DataFrame | pl.LazyFrame,
                chart_dict: dict[str, Any],
                param_dict: dict[str, Any],
                value_cols: list[str],
                width_col: str | None,
                colors: list[Any] | None = None,
                **subplot: Any,
            ) -> Any:
                if spec.get("plotter") != "plot_stacked_pareto_chart":
                    return original_plot_stacked_bar_width_plot(
                        df,
                        chart_dict,
                        param_dict,
                        value_cols,
                        width_col,
                        colors=colors,
                        **subplot,
                    )
                columns = LegacyPreparedDataCache._columns(df)
                if STACKED_PARETO_METRIC_LABEL_COLUMN not in columns:
                    return original_plot_stacked_bar_width_plot(
                        df,
                        chart_dict,
                        param_dict,
                        value_cols,
                        width_col,
                        colors=colors,
                        **subplot,
                    )
                class_order = [
                    names["aClassName"],
                    names["bClassName"],
                    names["cClassName"],
                    names["negativeClassName"],
                    names["lossClassName"],
                ]
                stack_cols = [
                    column
                    for column in value_cols
                    if column != STACKED_PARETO_METRIC_LABEL_COLUMN
                ]
                ordered_stack_cols = [
                    column for column in class_order if column in stack_cols
                ]
                ordered_stack_cols.extend(
                    column
                    for column in stack_cols
                    if column not in set(ordered_stack_cols)
                )
                result = original_plot_stacked_bar_width_plot(
                    df,
                    chart_dict,
                    param_dict,
                    ordered_stack_cols,
                    width_col,
                    colors=colors,
                    **subplot,
                )
                if isinstance(result, tuple) and result:
                    metric_names = [
                        str(item) for item in chart_dict[names["metricsToPlot"]]
                    ]
                    count_by_column = chart_dict.get(names["countByColumn"]) or (
                        f"{names['countName']} {chart_dict.get(names['countColumn'])}"
                    )
                    figure = _replace_stacked_pareto_total_annotations(
                        result[0],
                        _stacked_pareto_total_labels(df, chart_dict),
                    )
                    figure = _apply_stacked_pareto_axis_labels(
                        figure,
                        _stacked_pareto_axis_labels(
                            metric_names,
                            str(count_by_column),
                            chart_dict,
                            names,
                        ),
                    )
                    figure = _add_stacked_pareto_side_metric_annotations(
                        figure,
                        df,
                        chart_dict,
                        names,
                    )
                    result = (figure, *result[1:])
                return result

            def _prepare_locally_ordered_stacked_bar_small_multiples(
                df: pl.DataFrame | pl.LazyFrame,
                column: str,
                value_cols: list[str],
                chart_dict: dict[str, Any],
                param_dict: dict[str, Any],
                used_color_dict: dict[str, Any],
                global_unique_items: list[Any],
                father_and_child_items: list[Any],
                global_aggregate_other_items: list[Any],
                small_multiples_dimension: str,
                frame_array: list[pl.LazyFrame],
            ) -> tuple[
                pl.LazyFrame, dict[str, Any], list[str], str, list[pl.LazyFrame]
            ]:
                result = original_prepare_stacked_bar_small_multiples(
                    df,
                    column,
                    value_cols,
                    chart_dict,
                    param_dict,
                    used_color_dict,
                    global_unique_items,
                    father_and_child_items,
                    global_aggregate_other_items,
                    small_multiples_dimension,
                    frame_array,
                )
                if not _uses_local_stacked_bar_small_multiple_row_order(spec):
                    return result
                (
                    panel_frame,
                    result_chart,
                    color_array,
                    metric_to_plot,
                    result_frames,
                ) = result
                panel_frame = _locally_order_stacked_bar_small_multiple_rows(
                    panel_frame,
                    result_chart,
                    names,
                )
                return (
                    panel_frame,
                    result_chart,
                    color_array,
                    metric_to_plot,
                    result_frames,
                )

            def _stacked_pareto_title(
                df: Any,
                chosen_chart: str,
                param_dict: dict[str, Any],
                dimension: Any,
                title_metric: Any,
                chart_dict: dict[str, Any],
                period: Any,
                element: Any,
            ) -> tuple[str, dict[str, Any], dict[str, Any]]:
                if spec.get("plotter") != "plot_stacked_pareto_chart":
                    return original_plot_stacked_pareto_title(
                        df,
                        chosen_chart,
                        param_dict,
                        dimension,
                        title_metric,
                        chart_dict,
                        period,
                        element,
                    )
                if chart_dict.get(names["aggregateUniquesByDimension"]):
                    dimension = chart_dict.get(names["aggregateUniquesDimension"])
                else:
                    dimension = chart_dict.get(names["countColumn"])
                title_metrics = chart_dict.get(names["metricsToPlot"]) or [title_metric]
                title_metric = title_metrics[0]
                return original_plot_stacked_pareto_title(
                    df,
                    chosen_chart,
                    param_dict,
                    dimension,
                    title_metric,
                    chart_dict,
                    period,
                    element,
                )

            def _stacked_pareto_rank_others_as_last(
                df: pl.DataFrame | pl.LazyFrame,
                aggregate_other_items_name: str,
                rank_value: int,
            ) -> pl.LazyFrame:
                if (
                    spec.get("plotter") != "plot_stacked_pareto_chart"
                    or aggregate_other_items_name != names["workColumn"]
                ):
                    result = original_plot_rank_others_as_last(
                        df, aggregate_other_items_name, rank_value
                    )
                    if isinstance(df, pl.DataFrame) and isinstance(
                        result, pl.LazyFrame
                    ):
                        return LegacyPreparedDataCache._collect_frame(result)
                    return result
                frame = LegacyPreparedDataCache._collect_frame(df)
                columns = LegacyPreparedDataCache._columns(frame)
                if not columns:
                    return original_plot_rank_others_as_last(
                        frame, aggregate_other_items_name, rank_value
                    )
                label_col = columns[0]
                label_expr = pl.col(label_col).cast(pl.Utf8)
                metric_order = _stacked_pareto_metric_order(chart, names)
                order_frame = pl.DataFrame(
                    {
                        label_col: metric_order,
                        "__stacked_pareto_metric_order": list(range(len(metric_order))),
                    }
                )
                ordered = (
                    frame.with_row_index("__stacked_pareto_row")
                    .join(order_frame, on=label_col, how="left")
                    .with_columns(
                        pl.when(label_expr == names["workColumn"])
                        .then(pl.lit(1_000_000))
                        .otherwise(
                            pl.col("__stacked_pareto_metric_order").fill_null(
                                pl.col("__stacked_pareto_row")
                            )
                        )
                        .alias("__stacked_pareto_row_order")
                    )
                    .sort("__stacked_pareto_row_order")
                    .drop(
                        [
                            "__stacked_pareto_row",
                            "__stacked_pareto_metric_order",
                            "__stacked_pareto_row_order",
                        ]
                    )
                )
                if isinstance(df, pl.LazyFrame):
                    return ordered.lazy()
                return ordered

            def _ordered_color_pareto_classes(
                df: pl.DataFrame | pl.LazyFrame,
                metric: str,
                chart_dict: dict[str, Any],
                param_dict: dict[str, Any],
                color_name: str,
                ratio_name: str,
                class_name: str,
            ) -> tuple[pl.LazyFrame, dict[str, dict[str, str]], list[str]]:
                del param_dict
                colorpalette = names["colorpalette"]
                a_class_name = names["aClassName"]
                b_class_name = names["bClassName"]
                c_class_name = names["cClassName"]
                loss_class_name = names["lossClassName"]
                negative_class_name = names["negativeClassName"]
                margin_name = names["marginName"]
                color_dict = get_color_dictionary(chart_dict)
                color_array = list(color_dict[chart_dict[colorpalette]])
                while len(color_array) < 4:
                    color_array.append(color_array[-1] if color_array else "#818284")
                class_colors = {
                    a_class_name: color_array[0],
                    b_class_name: color_array[3],
                    c_class_name: color_array[1],
                }
                negative_class = (
                    loss_class_name if metric == margin_name else negative_class_name
                )
                class_color_dict: dict[str, dict[str, str]] = {
                    metric: {negative_class: color_dict["redColor"], **class_colors}
                }
                df_lazy = df.lazy() if isinstance(df, pl.DataFrame) else df
                df_lazy = df_lazy.with_columns(
                    pl.lit(None).cast(pl.Utf8).alias(color_name),
                    pl.lit(None).cast(pl.Utf8).alias(class_name),
                )
                negative_expr = pl.col(metric) < 0
                color_expr = pl.when(negative_expr).then(pl.lit(color_dict["redColor"]))
                class_expr = pl.when(negative_expr).then(pl.lit(negative_class))
                non_negative_metric = pl.col(metric) >= 0
                for limit, class_label in [
                    (0.80, a_class_name),
                    (0.95, b_class_name),
                    (200.0, c_class_name),
                ]:
                    condition = (pl.col(ratio_name) <= limit) & non_negative_metric
                    color_expr = color_expr.when(condition).then(
                        pl.lit(class_colors[class_label])
                    )
                    class_expr = class_expr.when(condition).then(pl.lit(class_label))
                df_lazy = df_lazy.with_columns(
                    color_expr.otherwise(pl.col(color_name)).alias(color_name),
                    class_expr.otherwise(pl.col(class_name)).alias(class_name),
                )
                color_list = (
                    LegacyPreparedDataCache._collect_frame(
                        df_lazy.select(pl.col(color_name).drop_nulls().unique())
                    )
                    .get_column(color_name)
                    .to_list()
                )
                return df_lazy, class_color_dict, color_list

            def _capturing_setup(
                df: Any,
                fig: Any,
                config_plotly_dict: dict[str, Any],
                chart_dict: dict[str, Any],
                string: Any,
                variance_analysis_chart: Any,
                run: Any,
                chosen_dimension: Any,
                param_dict: dict[str, Any],
            ) -> Any:
                if spec.get("capture_chart_data"):
                    derived_metrics = None
                    if spec.get("plotter") == "plot_stacked_pareto_chart":
                        derived_metrics = _stacked_pareto_unit_price_payload(
                            df, chart_dict, names
                        )
                    captured_chart_calls.append(
                        {
                            "call_index": len(captured_chart_calls) + 1,
                            "string": _json_safe(string),
                            "chosen_dimension": _json_safe(chosen_dimension),
                            "legacy_chart": chart_dict.get(names["chosenChart"]),
                            "data_frame": _frame_payload(df),
                            "derived_metrics": _json_safe(derived_metrics),
                        }
                    )
                return original_plot_charts_setup(
                    df,
                    fig,
                    config_plotly_dict,
                    chart_dict,
                    string,
                    variance_analysis_chart,
                    run,
                    chosen_dimension,
                    param_dict,
                )

            def _safe_timeline_setup(
                df: Any,
                fig: Any,
                config_plotly_dict: dict[str, Any],
                chart_dict: dict[str, Any],
                string: Any,
                variance_analysis_chart: Any,
                run: Any,
                chosen_dimension: Any,
                param_dict: dict[str, Any],
            ) -> Any:
                return original_draw_timeline_setup(
                    _safe_download_frame(df),
                    fig,
                    config_plotly_dict,
                    chart_dict,
                    string,
                    variance_analysis_chart,
                    run,
                    chosen_dimension,
                    param_dict,
                )

            if spec.get("capture_chart_data"):
                plot_charts_module.set_up_tab_for_show_or_download_chart = (
                    _capturing_setup
                )
                draw_width_and_stacked_plots.set_up_tab_for_show_or_download_chart = (
                    _capturing_setup
                )
            if spec.get("plotter") == "plot_timeline_charts":
                draw_timeline_module.set_up_tab_for_show_or_download_chart = (
                    _safe_timeline_setup
                )
            if spec.get("plotter") == "plot_mekko_charts":
                plot_charts_module.group_by_dataset_for_marimekko_and_barmekko = (
                    _cached_mekko_group
                )
                prepare_charts_module.group_by_dataset_for_marimekko_and_barmekko = (
                    _cached_mekko_group
                )
            plot_charts_module.group_by_dataset_for_stacked_bar = (
                _cached_stacked_bar_group
            )
            prepare_charts_module.group_by_dataset_for_stacked_bar = (
                _cached_stacked_bar_group
            )
            plot_charts_module.resample_dates = _cached_resample_dates
            prepare_charts_module.resample_dates = _cached_resample_dates
            plot_charts_module.show_only_largest = _cached_show_only_largest
            plot_charts_module.prepare_data_for_pareto = _cached_prepare_pareto
            plot_charts_module.rank_others_as_last = _stacked_pareto_rank_others_as_last
            plot_charts_module.stacked_bar_width_plot = _stacked_pareto_width_plot
            plot_charts_module.calculate_metrics_for_data_column = (
                _safe_calculate_metrics_for_data_column
            )
            stacked_column_prep.prepare_small_multiples_dataframe_for_stacked_bar = (
                _prepare_locally_ordered_stacked_bar_small_multiples
            )
            draw_width_and_stacked_plots.prepare_small_multiples_dataframe_for_stacked_bar = (
                _prepare_locally_ordered_stacked_bar_small_multiples
            )
            plot_charts_module.make_stacked_pareto_and_pareto_chart_title = (
                _stacked_pareto_title
            )
            plot_charts_module.transpose_chart_frame = _ordered_stacked_pareto_transpose
            plot_charts_module.make_df_for_pareto_classes = (
                _safe_make_df_for_pareto_classes
            )
            plot_charts_module.make_df_for_pareto_items = _safe_make_df_for_pareto_items
            misc_charts_data_prep.prepare_data_for_pareto = _cached_prepare_pareto
            misc_charts_data_prep.color_pareto_classes = _ordered_color_pareto_classes
            try:
                run_charting(
                    df_dict,
                    dimensions,
                    value_cols,
                    param,
                    chart,
                    _DummyTab(),
                    notifier=notifier,
                )
            except (
                AttributeError,
                ImportError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                pl.exceptions.PolarsError,
            ) as exc:
                return LegacyMixChartExport(
                    paths=[],
                    audit={
                        "status": "failed_legacy",
                        "chart": spec["name"],
                        "legacy_chart": chart[names["chosenChart"]],
                        "metrics_to_plot": chart.get(names["metricsToPlot"], []),
                        "value_cols": value_cols,
                        "x_metric": chart.get(names["xAxisMetric"]),
                        "y_metric": chart.get(names["yAxisMetric"]),
                        "multiplied_metric": chart.get(names["multipliedMetric"]),
                        "related_metrics_bar": bool(spec.get("related_metrics_bar")),
                        "primary_metric": (spec.get("metrics") or [None])[0],
                        "marker_metric": (
                            (spec.get("metrics") or [None, None])[1]
                            if len(spec.get("metrics") or []) > 1
                            else None
                        ),
                        "colorpalette": chart.get(names["colorpalette"]),
                        "show_absolute_values": chart.get(names["showAbsoluteValues"]),
                        **_legacy_chart_label_audit(names, chart),
                        "show_rank": chart.get(names["showRank"]),
                        "show_only": chart.get(names["showOnly"]),
                        "stacked_pareto_mode": spec.get("stacked_pareto_mode"),
                        "count_dimension": spec.get("count_dimension"),
                        "aggregate_uniques_by_dimension": spec.get(
                            "aggregate_uniques_by_dimension"
                        ),
                        "aggregate_uniques_dimension": spec.get(
                            "aggregate_uniques_dimension"
                        ),
                        **_cache_audit(),
                        "palette_policy": palette_policy,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "events": notifier.events,
                        "source_functions": source_functions,
                    },
                )
            finally:
                plot_charts_module.set_up_tab_for_show_or_download_chart = (
                    original_plot_charts_setup
                )
                draw_width_and_stacked_plots.set_up_tab_for_show_or_download_chart = (
                    original_draw_width_setup
                )
                draw_timeline_module.set_up_tab_for_show_or_download_chart = (
                    original_draw_timeline_setup
                )
                plot_charts_module.group_by_dataset_for_marimekko_and_barmekko = (
                    original_plot_mekko_group
                )
                prepare_charts_module.group_by_dataset_for_marimekko_and_barmekko = (
                    original_prepare_mekko_group
                )
                plot_charts_module.group_by_dataset_for_stacked_bar = (
                    original_plot_stacked_bar_group
                )
                prepare_charts_module.group_by_dataset_for_stacked_bar = (
                    original_prepare_stacked_bar_group
                )
                plot_charts_module.resample_dates = original_plot_resample_dates
                prepare_charts_module.resample_dates = original_prepare_resample_dates
                plot_charts_module.show_only_largest = original_plot_show_only_largest
                plot_charts_module.prepare_data_for_pareto = (
                    original_plot_prepare_pareto
                )
                plot_charts_module.rank_others_as_last = (
                    original_plot_rank_others_as_last
                )
                plot_charts_module.stacked_bar_width_plot = (
                    original_plot_stacked_bar_width_plot
                )
                plot_charts_module.calculate_metrics_for_data_column = (
                    original_plot_calculate_data_column_metrics
                )
                stacked_column_prep.prepare_small_multiples_dataframe_for_stacked_bar = (
                    original_prepare_stacked_bar_small_multiples
                )
                draw_width_and_stacked_plots.prepare_small_multiples_dataframe_for_stacked_bar = (
                    original_draw_prepare_stacked_bar_small_multiples
                )
                plot_charts_module.make_stacked_pareto_and_pareto_chart_title = (
                    original_plot_stacked_pareto_title
                )
                plot_charts_module.transpose_chart_frame = (
                    original_plot_transpose_chart_frame
                )
                plot_charts_module.make_df_for_pareto_classes = (
                    original_plot_make_pareto_classes
                )
                plot_charts_module.make_df_for_pareto_items = (
                    original_plot_make_pareto_items
                )
                misc_charts_data_prep.prepare_data_for_pareto = (
                    original_misc_prepare_pareto
                )
                misc_charts_data_prep.color_pareto_classes = (
                    original_misc_color_pareto_classes
                )
                stacked_column_prep.modify_color_array = original_modify_color_array
        error_events = [
            event
            for event in notifier.events
            if event.get("method") == "error" or event.get("level") == "error"
        ]
        warning_events = [
            event
            for event in error_events
            if _is_small_multiple_total_warning(event, spec)
        ]
        blocking_error_events = [
            event for event in error_events if event not in warning_events
        ]
        if blocking_error_events or (error_events and not notifier.figures):
            return LegacyMixChartExport(
                paths=[],
                audit={
                    "status": "failed_legacy_caught",
                    "chart": spec["name"],
                    "legacy_chart": chart[names["chosenChart"]],
                    "metrics_to_plot": chart.get(names["metricsToPlot"], []),
                    "value_cols": value_cols,
                    "x_metric": chart.get(names["xAxisMetric"]),
                    "y_metric": chart.get(names["yAxisMetric"]),
                    "multiplied_metric": chart.get(names["multipliedMetric"]),
                    "related_metrics_bar": bool(spec.get("related_metrics_bar")),
                    "primary_metric": (spec.get("metrics") or [None])[0],
                    "marker_metric": (
                        (spec.get("metrics") or [None, None])[1]
                        if len(spec.get("metrics") or []) > 1
                        else None
                    ),
                    "colorpalette": chart.get(names["colorpalette"]),
                    "show_absolute_values": chart.get(names["showAbsoluteValues"]),
                    **_legacy_chart_label_audit(names, chart),
                    "show_rank": chart.get(names["showRank"]),
                    "show_only": chart.get(names["showOnly"]),
                    **_cache_audit(),
                    "palette_policy": palette_policy,
                    "error_events": blocking_error_events,
                    "warning_events": warning_events,
                    "events": notifier.events,
                    "source_functions": source_functions,
                },
            )
        figures_for_export = notifier.figures
        calls_for_context = captured_chart_calls
        if spec.get("capture_figure") == "last" and notifier.figures:
            figures_for_export = notifier.figures[-1:]
            calls_for_context = captured_chart_calls[-1:]
            notifier.figures = figures_for_export
        elif spec.get("capture_figure") == "first" and notifier.figures:
            figures_for_export = notifier.figures[:1]
            calls_for_context = captured_chart_calls[:1]
            notifier.figures = figures_for_export
        if spec.get("synthesis_plot"):
            _apply_synthesis_dimension_labels(
                figures_for_export, [str(item) for item in spec.get("dimensions") or []]
            )
        if uniform_synthesis_palette:
            _apply_uniform_synthesis_palette(figures_for_export)
        if spec.get("related_metrics_bar"):
            _apply_related_metric_marker_color(figures_for_export)
        if spec.get("total_column_dimension"):
            _clear_total_column_bar_text(figures_for_export, spec)
            _apply_total_column_cagr_annotation(
                figures_for_export,
                chart,
                names,
                draw_width_and_stacked_plots.add_first_row_annotations_for_stacked_column,
                (
                    "CAGR"
                    if str(spec.get("period_grain") or "").lower() == "year"
                    else None
                ),
            )
        _apply_display_dimension_label(figures_for_export, spec)
        _unwrap_cohort_label_annotations(figures_for_export, spec)
        _suppress_stacked_percentage_labels(figures_for_export, spec)
        _spread_cohort_label_annotations(figures_for_export, spec)
        _apply_stacked_total_cagr_annotation(
            figures_for_export,
            spec,
            period_totals,
            selected_periods,
        )
        _apply_stacked_bar_small_multiple_readable_canvas(figures_for_export, spec)
        _apply_barmekko_small_multiple_label_canvas(figures_for_export, spec)
        _apply_period_window_title_context(figures_for_export, period_adapter_audit)
        _apply_period_display_label_to_titles(figures_for_export, spec)
        _apply_period_window_axis_labels(figures_for_export, period_adapter_audit)
        _apply_reporting_title_structure(figures_for_export, spec, period_adapter_audit)
        if render:
            paths, exports = _write_captured_figures(
                notifier,
                output_dir,
                str(spec["artifact_name"]),
            )
        else:
            paths = []
            exports = []
        if render and not paths:
            return LegacyMixChartExport(
                paths=[],
                audit={
                    "status": "not_written_legacy_no_figure",
                    "chart": spec["name"],
                    "legacy_chart": chart[names["chosenChart"]],
                    "metrics_to_plot": chart.get(names["metricsToPlot"], []),
                    "value_cols": value_cols,
                    "x_metric": chart.get(names["xAxisMetric"]),
                    "y_metric": chart.get(names["yAxisMetric"]),
                    "multiplied_metric": chart.get(names["multipliedMetric"]),
                    "related_metrics_bar": bool(spec.get("related_metrics_bar")),
                    "primary_metric": (spec.get("metrics") or [None])[0],
                    "marker_metric": (
                        (spec.get("metrics") or [None, None])[1]
                        if len(spec.get("metrics") or []) > 1
                        else None
                    ),
                    "colorpalette": chart.get(names["colorpalette"]),
                    "show_absolute_values": chart.get(names["showAbsoluteValues"]),
                    **_legacy_chart_label_audit(names, chart),
                    "show_rank": chart.get(names["showRank"]),
                    "show_only": chart.get(names["showOnly"]),
                    **_cache_audit(),
                    "palette_policy": palette_policy,
                    "error_events": [],
                    "warning_events": warning_events,
                    "events": notifier.events,
                    "source_functions": source_functions,
                },
            )
    chart_context = _capture_context_payload(
        spec=spec,
        chart=chart,
        calls=calls_for_context,
        figures=figures_for_export,
        exports=exports,
        source_functions=source_functions,
    )
    return LegacyMixChartExport(
        paths=paths,
        audit={
            "status": "written" if render else "data_written",
            "chart": spec["name"],
            "legacy_chart": chart[names["chosenChart"]],
            "rendered": render,
            "metrics_to_plot": chart.get(names["metricsToPlot"], []),
            "value_cols": value_cols,
            "x_metric": chart.get(names["xAxisMetric"]),
            "y_metric": chart.get(names["yAxisMetric"]),
            "multiplied_metric": chart.get(names["multipliedMetric"]),
            "related_metrics_bar": bool(spec.get("related_metrics_bar")),
            "primary_metric": (spec.get("metrics") or [None])[0],
            "marker_metric": (
                (spec.get("metrics") or [None, None])[1]
                if len(spec.get("metrics") or []) > 1
                else None
            ),
            "colorpalette": chart.get(names["colorpalette"]),
            "show_absolute_values": chart.get(names["showAbsoluteValues"]),
            **_legacy_chart_label_audit(names, chart),
            "show_rank": chart.get(names["showRank"]),
            "show_only": chart.get(names["showOnly"]),
            **_cache_audit(),
            "palette_policy": palette_policy,
            "exports": exports,
            "dimensions": spec.get("dimensions") or [],
            "x_dimension": spec.get("x_dimension"),
            "y_dimension": spec.get("y_dimension"),
            "small_multiples_dimension": spec.get("small_multiples_dimension"),
            "selected_periods": selected_periods,
            "period_grain": spec.get("period_grain"),
            "period_window": spec.get("period_window") or {},
            "period_comparison_mode": spec.get("period_comparison_mode"),
            "period_adapter": period_adapter_audit,
            "period_selection_mode": spec.get("period_selection_mode"),
            "dimension_selection": spec.get("dimension_selection"),
            "stacked_pareto_mode": spec.get("stacked_pareto_mode"),
            "count_dimension": spec.get("count_dimension"),
            "aggregate_uniques_by_dimension": spec.get(
                "aggregate_uniques_by_dimension"
            ),
            "aggregate_uniques_dimension": spec.get("aggregate_uniques_dimension"),
            "focus_item": spec.get("focus_item"),
            "focus_dimension": spec.get("focus_dimension"),
            "focus_status": spec.get("focus_status"),
            "focus_reason": spec.get("focus_reason"),
            "share_view": bool(spec.get("share_view")),
            "warning_events": warning_events,
            "events": notifier.events,
            "source_functions": source_functions,
        },
        chart_context=chart_context,
    )
