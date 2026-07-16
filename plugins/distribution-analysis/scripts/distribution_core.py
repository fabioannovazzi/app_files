"""Core workflow for the distribution-analysis Codex plugin."""

from __future__ import annotations

import argparse
import calendar
import json
import logging
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import polars as pl
from legacy_distribution_charting import (
    CANONICAL_DATE,
    CANONICAL_PERIOD,
    CURRENT_PERIOD,
    LegacyPreparedDataCache,
    cleanup_legacy_imports,
    ensure_legacy_import_path,
    write_legacy_distribution_chart,
)

SCRIPT_DIR = Path(__file__).resolve().parent


def _ensure_local_review_session_import() -> None:
    """Use this plugin's review-session module in multi-plugin test runs."""

    script_dir = str(SCRIPT_DIR)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    module = sys.modules.get("review_session")
    module_file = getattr(module, "__file__", None) if module is not None else None
    if module_file and Path(module_file).resolve().is_relative_to(SCRIPT_DIR.resolve()):
        return
    if module is not None:
        del sys.modules["review_session"]


_ensure_local_review_session_import()
from review_session import write_review_session_artifacts, write_run_intake

ensure_legacy_import_path()
from modules.chart_harness import (  # noqa: E402  # isort: skip
    apply_recipe_filters,
    apply_recipe_cohorts,
    available_analysis_context,
    calendar_period_label,
    PERIOD_TYPE_CALENDAR,
    PERIOD_TYPE_FISCAL,
    PERIOD_TYPE_ROLLING,
    PERIOD_TYPE_TO_DATE,
    period_contract_options,
    period_label_expression,
    preserve_recipe_cohorts,
    preserve_recipe_filters,
    recipe_cohort_period_labels,
    recipe_cohort_source_dimensions,
    reporting_entity_label_from_recipe,
    reporting_subject_label_from_recipe,
    write_prepared_data_manifest,
)
from modules.utilities.helpers import get_schema_and_column_names
from modules.utilities.utils import get_row_count

__all__ = [
    "SCHEMA_VERSION",
    "DistributionRunResult",
    "add_common_args",
    "build_chart_specs",
    "build_recipe",
    "configure_logging",
    "inspect_distribution_inputs",
    "prepare_canonical_frame",
    "read_json",
    "read_table",
    "run_distribution",
    "write_json",
]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "1.0"
DEFAULT_DATE = datetime(2026, 1, 1, tzinfo=UTC).date()
DEFAULT_ROLLING_WINDOW_MONTHS = 12
ROLLING_PERIOD_SYMBOL = "~"
ARTIFACT_MODE_DATA_ONLY = "data_only"
ARTIFACT_MODE_DATA_AND_RENDER = "data_and_render"
ARTIFACT_MODES = {
    ARTIFACT_MODE_DATA_ONLY,
    ARTIFACT_MODE_DATA_AND_RENDER,
}
CSV_EXTENSIONS = {".csv", ".tsv", ".psv", ".txt"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
SUPPORTED_DISTRIBUTION_CHARTS: dict[str, dict[str, str]] = {
    "histogram": {
        "legacy_chart_key": "histogramChart",
        "plotter": "plot_histogram_charts",
        "artifact": "histogram.png",
    },
    "boxplot": {
        "legacy_chart_key": "boxplotChart",
        "plotter": "plot_boxplot_charts",
        "artifact": "boxplot.png",
    },
    "stripplot": {
        "legacy_chart_key": "stripplotChart",
        "plotter": "plot_stripplot_charts",
        "artifact": "stripplot.png",
    },
    "ecdf": {
        "legacy_chart_key": "ecdfChart",
        "plotter": "plot_ecdf_charts",
        "artifact": "ecdf.png",
    },
    "kernel_density": {
        "legacy_chart_key": "kernelDensityChart",
        "plotter": "plot_kernel_density_charts",
        "artifact": "kernel_density.png",
    },
}


@dataclass(frozen=True)
class DistributionRunResult:
    """Result object returned by ``run_distribution``."""

    canonical_frame: pl.DataFrame
    audit: dict[str, Any]
    summary_markdown: str
    artifact_paths: list[str]


def utc_now() -> str:
    """Return the current UTC timestamp."""

    return datetime.now(UTC).isoformat()


def configure_logging(verbose: bool = False) -> None:
    """Configure plugin logging."""

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common CLI arguments for plugin scripts."""

    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--language", default="en")
    parser.add_argument("--currency", default=None)
    parser.add_argument(
        "--artifact-mode",
        choices=sorted(ARTIFACT_MODES),
        default=ARTIFACT_MODE_DATA_AND_RENDER,
        help=(
            "Write chart data/context only or keep the legacy data-and-render behavior."
        ),
    )
    parser.add_argument("--verbose", action="store_true")


def default_output_dir(input_file: Path) -> Path:
    """Return the safe default output directory next to the input file."""

    return input_file.expanduser().resolve().parent / "output" / "distribution-analysis"


def json_safe(value: Any) -> Any:
    """Return JSON-safe values for common analysis objects."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (Path, datetime)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, TypeError, ValueError):
            return str(value)
    return value


def read_json(path: Path | None) -> dict[str, Any] | None:
    """Read a JSON object from ``path`` when provided."""

    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON file with deterministic formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _collect_csv_scan(path: Path, *, separator: str) -> pl.DataFrame:
    """Read delimited input through a lazy scan and collect once."""

    lf = pl.scan_csv(path, separator=separator, infer_schema_length=10000)
    try:
        return lf.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return lf.collect()


def read_table(path: Path) -> pl.DataFrame:
    """Read CSV/TSV/PSV or Excel data into a Polars DataFrame."""

    suffix = path.suffix.lower()
    if suffix in CSV_EXTENSIONS:
        separator = ","
        if suffix == ".tsv":
            separator = "\t"
        elif suffix == ".psv":
            separator = "|"
        return _collect_csv_scan(path, separator=separator)
    if suffix in EXCEL_EXTENSIONS:
        return pl.read_excel(path)
    raise ValueError(f"Unsupported input extension: {suffix}")


def _is_numeric_dtype(dtype: pl.DataType) -> bool:
    return bool(getattr(dtype, "is_numeric", lambda: False)())


def _is_date_dtype(dtype: pl.DataType) -> bool:
    return dtype in {pl.Date, pl.Datetime}


def _normalize_name(name: str) -> str:
    return " ".join(name.replace("_", " ").replace("-", " ").lower().split())


def _compact_name(name: str) -> str:
    return "".join(_normalize_name(name).split())


def _first_matching_column(columns: Iterable[str], hints: Iterable[str]) -> str | None:
    normalized = [
        (column, _normalize_name(column), _compact_name(column)) for column in columns
    ]
    hint_values = [(_normalize_name(hint), _compact_name(hint)) for hint in hints]
    for hint, compact_hint in hint_values:
        for column, column_name, column_compact in normalized:
            if column_name == hint or column_compact == compact_hint:
                return column
    for hint, compact_hint in hint_values:
        for column, column_name, column_compact in normalized:
            if hint in column_name or compact_hint in column_compact:
                return column
    return None


def _numeric_columns(frame: pl.DataFrame) -> list[str]:
    _columns, schema = get_schema_and_column_names(frame)
    return [
        name
        for name, dtype in schema.items()
        if _is_numeric_dtype(dtype) and not _normalize_name(name).endswith("id")
    ]


def _unique_count(frame: pl.DataFrame, column: str) -> int:
    return int(frame.select(pl.col(column).n_unique()).item() or 0)


def _dimension_candidates(frame: pl.DataFrame, numeric_columns: set[str]) -> list[str]:
    columns, schema = get_schema_and_column_names(frame)
    result: list[str] = []
    for column in columns:
        if column in numeric_columns or column in {CANONICAL_DATE, CANONICAL_PERIOD}:
            continue
        if _is_date_dtype(schema[column]):
            continue
        unique_count = _unique_count(frame, column)
        if 1 < unique_count <= max(get_row_count(frame), 2):
            result.append(column)
    preferred = ("brand", "product", "item", "company", "customer", "retailer")
    return sorted(
        result,
        key=lambda column: (
            (
                0
                if any(keyword in _normalize_name(column) for keyword in preferred)
                else 1
            ),
            _unique_count(frame, column),
            column.lower(),
        ),
    )


def _date_column(columns: list[str], schema: dict[str, pl.DataType]) -> str | None:
    for column in columns:
        if _is_date_dtype(schema[column]):
            return column
    return _first_matching_column(columns, ["date", "order date", "month"])


def _period_column(columns: list[str]) -> str | None:
    return _first_matching_column(
        columns,
        ["period", "scenario", "version", "actual plan", "actual vs plan"],
    )


def _coalesce_mapping(
    mappings: dict[str, Any],
    key: str,
    fallback: str | None,
) -> str | None:
    value = mappings[key] if key in mappings else None
    return str(value) if value else fallback


def _period_values(frame: pl.DataFrame, period_column: str | None) -> list[str]:
    if period_column is None:
        return [CURRENT_PERIOD]
    rows = (
        frame.select(pl.col(period_column).cast(pl.Utf8).alias(period_column))
        .drop_nulls()
        .unique(maintain_order=True)
        .to_series()
        .to_list()
    )
    values = [str(value) for value in rows if value is not None]
    if not values:
        return [CURRENT_PERIOD]
    preferred = [value for value in ["PY", CURRENT_PERIOD] if value in values]
    if len(preferred) >= 2:
        return preferred
    return values[:2]


def _parse_date_expression(column: str) -> pl.Expr:
    expr = pl.col(column)
    return expr.cast(pl.Date, strict=False).fill_null(
        expr.cast(pl.Utf8)
        .str.strptime(pl.Date, strict=False)
        .fill_null(
            expr.cast(pl.Utf8).str.strptime(pl.Datetime, strict=False).cast(pl.Date)
        )
    )


def _coerce_date_value(value: Any) -> date | None:
    """Return a plain ``date`` from common Polars/Python date values."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _date_values(frame: pl.DataFrame, date_column: str | None) -> list[date]:
    """Return sorted unique source dates from ``date_column``."""

    columns, _schema = get_schema_and_column_names(frame)
    if not date_column or date_column not in columns:
        return []
    values = (
        frame.select(_parse_date_expression(str(date_column)).alias(CANONICAL_DATE))
        .drop_nulls()
        .unique(maintain_order=True)
        .sort(CANONICAL_DATE)
        .to_series()
        .to_list()
    )
    return [value for value in (_coerce_date_value(item) for item in values) if value]


def _add_months(value: date, months: int) -> date:
    """Return ``value`` shifted by whole months, clamping invalid month days."""

    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _period_window_label(symbol: str, end_date: date) -> str:
    """Return the legacy rolling/YTD month-year period label."""

    return f"{symbol}{end_date.strftime('%b-%Y')}"


def _rolling_period_plan(
    dates: list[date],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Return a rolling prior-year period plan for date-only inputs."""

    if not dates:
        return {
            "status": "skipped",
            "reason": "no_usable_date_values",
            "selected_periods": [CURRENT_PERIOD],
        }
    try:
        window_months = int(
            options.get("rolling_window_months") or DEFAULT_ROLLING_WINDOW_MONTHS
        )
    except (TypeError, ValueError):
        window_months = DEFAULT_ROLLING_WINDOW_MONTHS
    window_months = max(1, window_months)
    comparison_end = max(dates)
    comparison_start = _add_months(comparison_end, -(window_months - 1)).replace(day=1)
    baseline_start = _add_months(comparison_start, -12)
    baseline_end = _add_months(comparison_end, -12)
    baseline_label = _period_window_label(ROLLING_PERIOD_SYMBOL, baseline_end)
    comparison_label = _period_window_label(ROLLING_PERIOD_SYMBOL, comparison_end)
    baseline_date_count = sum(
        1 for value in dates if baseline_start <= value <= baseline_end
    )
    comparison_date_count = sum(
        1 for value in dates if comparison_start <= value <= comparison_end
    )
    selected_periods = (
        [baseline_label, comparison_label]
        if baseline_date_count
        else [comparison_label]
    )
    return {
        "status": "applied" if comparison_date_count else "skipped",
        "reason": (
            "date_column_without_period_column"
            if comparison_date_count
            else "no_rows_in_current_window"
        ),
        "period_comparison_mode": "rolling_period",
        "rolling_window_months": window_months,
        "selected_periods": selected_periods,
        "comparison": {
            "label": comparison_label,
            "start_date": comparison_start.isoformat(),
            "end_date": comparison_end.isoformat(),
            "date_count": comparison_date_count,
        },
        "baseline": (
            {
                "label": baseline_label,
                "start_date": baseline_start.isoformat(),
                "end_date": baseline_end.isoformat(),
                "date_count": baseline_date_count,
            }
            if baseline_date_count
            else None
        ),
    }


def _calendar_period_plan(
    dates: list[date],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Return a calendar/fiscal period labeling plan for date-only inputs."""

    if not dates:
        return {
            "status": "skipped",
            "reason": "no_usable_date_values",
            "selected_periods": [CURRENT_PERIOD],
        }
    contract = period_contract_options(options)
    period_type = str(contract["period_type"])
    fiscal_start_month = (
        int(contract["fiscal_start_month"]) if period_type == PERIOD_TYPE_FISCAL else 1
    )
    period_grain = str(contract["period_grain"])
    labels = [
        calendar_period_label(
            value,
            period_grain=period_grain,
            fiscal_start_month=fiscal_start_month,
        )
        for value in dates
    ]
    unique_labels = list(dict.fromkeys(labels))
    latest_label = labels[-1]
    return {
        "status": "applied",
        "reason": "date_column_without_period_column",
        "period_type": period_type,
        "period_grain": period_grain,
        "fiscal_start_month": fiscal_start_month,
        "selected_periods": [latest_label],
        "available_periods": unique_labels,
    }


def _to_date_period_plan(
    dates: list[date],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Return a current/prior-year to-date period plan for date-only inputs."""

    if not dates:
        return {
            "status": "skipped",
            "reason": "no_usable_date_values",
            "selected_periods": [CURRENT_PERIOD],
        }
    contract = period_contract_options(options, default_type=PERIOD_TYPE_TO_DATE)
    comparison_end = max(dates)
    fiscal_start_month = int(contract["fiscal_start_month"])
    comparison_year = (
        comparison_end.year
        if comparison_end.month >= fiscal_start_month
        else comparison_end.year - 1
    )
    comparison_start = date(comparison_year, fiscal_start_month, 1)
    baseline_start = _add_months(comparison_start, -12)
    baseline_end = _add_months(comparison_end, -12)
    comparison_label = _period_window_label("_", comparison_end)
    baseline_label = _period_window_label("_", baseline_end)
    baseline_date_count = sum(
        1 for value in dates if baseline_start <= value <= baseline_end
    )
    comparison_date_count = sum(
        1 for value in dates if comparison_start <= value <= comparison_end
    )
    selected_periods = (
        [baseline_label, comparison_label]
        if baseline_date_count
        else [comparison_label]
    )
    return {
        "status": "applied" if comparison_date_count else "skipped",
        "reason": (
            "date_column_without_period_column"
            if comparison_date_count
            else "no_rows_in_current_to_date_window"
        ),
        "period_type": PERIOD_TYPE_TO_DATE,
        "period_grain": str(contract["period_grain"]),
        "fiscal_start_month": fiscal_start_month,
        "period_comparison_mode": "year_to_date",
        "selected_periods": selected_periods,
        "comparison": {
            "label": comparison_label,
            "start_date": comparison_start.isoformat(),
            "end_date": comparison_end.isoformat(),
            "date_count": comparison_date_count,
        },
        "baseline": (
            {
                "label": baseline_label,
                "start_date": baseline_start.isoformat(),
                "end_date": baseline_end.isoformat(),
                "date_count": baseline_date_count,
            }
            if baseline_date_count
            else None
        ),
    }


def _date_period_plan(
    dates: list[date],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Return the period derivation plan requested for date-only inputs."""

    contract = period_contract_options(options, default_type=PERIOD_TYPE_ROLLING)
    period_type = str(contract["period_type"])
    if period_type == PERIOD_TYPE_ROLLING:
        plan = _rolling_period_plan(dates, options)
        plan.setdefault("period_type", PERIOD_TYPE_ROLLING)
        plan.setdefault("period_grain", contract["period_grain"])
        return plan
    if period_type == PERIOD_TYPE_TO_DATE:
        return _to_date_period_plan(dates, options)
    if period_type in {PERIOD_TYPE_CALENDAR, PERIOD_TYPE_FISCAL}:
        return _calendar_period_plan(dates, options)
    return {
        "status": "skipped",
        "reason": "unsupported_date_period_type",
        "period_type": period_type,
        "selected_periods": [CURRENT_PERIOD],
    }


def _selected_periods_from_options(options: dict[str, Any]) -> list[str]:
    return [str(item) for item in options.get("selected_periods") or [] if item]


def _selected_periods_for_recipe(
    frame: pl.DataFrame,
    *,
    date_column: str | None,
    period_column: str | None,
    options: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Return selected periods and an audit for period-bucket inference."""

    requested_periods = _selected_periods_from_options(options)
    if period_column:
        inferred = _period_values(frame, period_column)
        contract = period_contract_options(options)
        return requested_periods or inferred, {
            "status": "explicit_period_column",
            "period_column": period_column,
            "period_type": contract["period_type"],
            "period_grain": contract["period_grain"],
            "selected_periods": requested_periods or inferred,
        }
    if date_column:
        plan = _date_period_plan(_date_values(frame, date_column), options)
        if plan["status"] == "applied":
            inferred_periods = [str(item) for item in plan["selected_periods"]]
            available_periods = [
                str(item) for item in plan.get("available_periods") or inferred_periods
            ]
            if requested_periods and requested_periods != [CURRENT_PERIOD]:
                requested_set = set(requested_periods)
                if requested_set.issubset(set(available_periods)):
                    return requested_periods, {
                        **plan,
                        "selected_periods": requested_periods,
                        "requested_selected_periods": requested_periods,
                    }
            return inferred_periods, plan
    return requested_periods or [CURRENT_PERIOD], {
        "status": "single_actual_fallback",
        "reason": "no_period_column_or_usable_date_column",
        "selected_periods": requested_periods or [CURRENT_PERIOD],
    }


def _apply_rolling_period_plan(
    canonical: pl.DataFrame,
    plan: dict[str, Any],
) -> pl.DataFrame:
    """Relabel canonical rows into rolling/to-date windows from ``plan``."""

    if plan.get("status") != "applied":
        return canonical
    comparison = plan.get("comparison") or {}
    baseline = plan.get("baseline") or {}
    comparison_label = comparison.get("label")
    comparison_start = _coerce_date_value(comparison.get("start_date"))
    comparison_end = _coerce_date_value(comparison.get("end_date"))
    if not comparison_label or not comparison_start or not comparison_end:
        return canonical
    date_expr = pl.col(CANONICAL_DATE).cast(pl.Date)
    label_expr = pl.when(
        (date_expr >= pl.lit(comparison_start)) & (date_expr <= pl.lit(comparison_end))
    ).then(pl.lit(str(comparison_label)))
    baseline_label = baseline.get("label")
    baseline_start = _coerce_date_value(baseline.get("start_date"))
    baseline_end = _coerce_date_value(baseline.get("end_date"))
    if baseline_label and baseline_start and baseline_end:
        label_expr = label_expr.when(
            (date_expr >= pl.lit(baseline_start)) & (date_expr <= pl.lit(baseline_end))
        ).then(pl.lit(str(baseline_label)))
    return canonical.with_columns(
        label_expr.otherwise(None).alias(CANONICAL_PERIOD)
    ).filter(pl.col(CANONICAL_PERIOD).is_not_null())


def _apply_date_period_plan(
    canonical: pl.DataFrame,
    plan: dict[str, Any],
) -> pl.DataFrame:
    """Relabel canonical rows using a date-only period derivation plan."""

    period_type = str(plan.get("period_type") or "")
    if period_type in {PERIOD_TYPE_CALENDAR, PERIOD_TYPE_FISCAL}:
        fiscal_start_month = int(plan.get("fiscal_start_month") or 1)
        return canonical.with_columns(
            period_label_expression(
                pl.col(CANONICAL_DATE).cast(pl.Date),
                period_grain=str(plan.get("period_grain") or "year"),
                fiscal_start_month=fiscal_start_month,
            ).alias(CANONICAL_PERIOD)
        )
    return _apply_rolling_period_plan(canonical, plan)


def _resolve_small_multiples_dimension(
    distribution_dimension: str | None,
    small_multiples_dimension: str | None,
    candidate_dimensions: list[str],
    candidate_unique_counts: dict[str, int],
    max_panel_count: int,
) -> tuple[str | None, dict[str, Any]]:
    """Resolve the small-multiple facet to a non-redundant, readable dimension."""

    requested = (
        str(small_multiples_dimension).strip()
        if small_multiples_dimension is not None
        else None
    )
    primary = (
        str(distribution_dimension).strip()
        if distribution_dimension is not None
        else None
    )
    if not requested:
        return None, {
            "status": "not_requested",
            "reason": "no_small_multiples_dimension",
            "distribution_dimension": primary,
            "requested_small_multiples_dimension": requested,
            "resolved_small_multiples_dimension": None,
        }
    # This is mechanically invalid: a small multiple must add a second cut.
    if primary and requested == primary:
        alternatives = [
            dimension
            for dimension in candidate_dimensions
            if dimension and dimension != primary
        ]
        ranked_alternatives = sorted(
            alternatives,
            key=lambda dimension: (
                (
                    0
                    if 1 < candidate_unique_counts.get(dimension, 0) <= max_panel_count
                    else 1
                ),
                candidate_unique_counts.get(dimension, 0),
                alternatives.index(dimension),
            ),
        )
        if ranked_alternatives:
            resolved = ranked_alternatives[0]
            return resolved, {
                "status": "resolved_alternative_dimension",
                "reason": (
                    "requested small_multiples_dimension repeated "
                    "distribution_dimension"
                ),
                "distribution_dimension": primary,
                "requested_small_multiples_dimension": requested,
                "resolved_small_multiples_dimension": resolved,
                "candidate_unique_counts": {
                    dimension: candidate_unique_counts.get(dimension)
                    for dimension in alternatives
                },
            }
        return None, {
            "status": "disabled_no_alternative_dimension",
            "reason": (
                "small_multiples_dimension must differ from distribution_dimension"
            ),
            "distribution_dimension": primary,
            "requested_small_multiples_dimension": requested,
            "resolved_small_multiples_dimension": None,
            "candidate_unique_counts": {},
        }
    return requested, {
        "status": "kept",
        "reason": "small_multiples_dimension_adds_second_cut",
        "distribution_dimension": primary,
        "requested_small_multiples_dimension": requested,
        "resolved_small_multiples_dimension": requested,
    }


def build_recipe(
    input_path: Path,
    frame: pl.DataFrame,
    *,
    language: str = "en",
    currency: str | None = None,
    existing_recipe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer or merge the recipe needed by the distribution workflow."""

    columns, schema = get_schema_and_column_names(frame)
    numeric_columns = _numeric_columns(frame)
    if not numeric_columns:
        raise ValueError("Distribution charts require at least one numeric metric.")
    dimensions = _dimension_candidates(frame, set(numeric_columns))
    dimension_unique_counts = {
        dimension: _unique_count(frame, dimension) for dimension in dimensions
    }
    date_column = _date_column(columns, schema)
    period_column = _period_column(columns)
    mappings = dict((existing_recipe or {}).get("mappings") or {})
    options = dict((existing_recipe or {}).get("options") or {})
    metric_column = _coalesce_mapping(
        mappings,
        "metric_column",
        _first_matching_column(
            numeric_columns,
            ["sales", "revenue", "amount", "value", "price", "units", "quantity"],
        )
        or numeric_columns[0],
    )
    distribution_dimension = _coalesce_mapping(
        mappings,
        "distribution_dimension",
        None,
    )
    small_multiples_dimension = _coalesce_mapping(
        mappings,
        "small_multiples_dimension",
        dimensions[0] if dimensions else None,
    )
    (
        small_multiples_dimension,
        small_multiples_dimension_audit,
    ) = _resolve_small_multiples_dimension(
        distribution_dimension,
        small_multiples_dimension,
        dimensions,
        dimension_unique_counts,
        int(
            options.get("small_multiples_max_panels")
            or min(int(options.get("max_chart_items") or 8), 6)
        ),
    )
    selected_periods, period_bucketing_audit = _selected_periods_for_recipe(
        frame,
        date_column=date_column,
        period_column=period_column,
        options=options,
    )
    normalized_period_contract = period_contract_options(
        options,
        default_type=str(
            period_bucketing_audit.get("period_type") or PERIOD_TYPE_ROLLING
        ),
    )
    recipe = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "distribution-analysis",
        "input_file": str(input_path),
        "language": (existing_recipe or {}).get("language") or language,
        "mappings": {
            "metric_column": metric_column,
            "distribution_dimension": distribution_dimension,
            "small_multiples_dimension": small_multiples_dimension,
            "date_column": _coalesce_mapping(mappings, "date_column", date_column),
            "period_column": _coalesce_mapping(
                mappings, "period_column", period_column
            ),
            "dimensions": list(
                dict.fromkeys(
                    item
                    for item in [
                        distribution_dimension,
                        small_multiples_dimension,
                        *dimensions,
                    ]
                    if item
                )
            ),
        },
        "options": {
            "currency": currency or options.get("currency") or "EUR",
            "charts": options.get("charts") or list(SUPPORTED_DISTRIBUTION_CHARTS),
            "selected_periods": selected_periods,
            "period_type": normalized_period_contract["period_type"],
            "period_grain": normalized_period_contract["period_grain"],
            "fiscal_start_month": normalized_period_contract["fiscal_start_month"],
            "period_bucketing_audit": period_bucketing_audit,
            "small_multiples": options.get("small_multiples", True),
            "small_multiples_dimension_audit": small_multiples_dimension_audit,
            "max_chart_items": int(options.get("max_chart_items") or 8),
            "aggregate_other_items": options.get("aggregate_other_items", True),
            "cumulative_histogram": options.get("cumulative_histogram", False),
            "reversed_ecdf": options.get("reversed_ecdf", False),
            "show_outliers": options.get("show_outliers", True),
            "log_x_axis": options.get("log_x_axis", False),
        },
        "inspection": {
            "row_count": get_row_count(frame),
            "column_count": frame.width,
            "columns": columns,
            "schema": {name: str(dtype) for name, dtype in schema.items()},
            "numeric_columns": numeric_columns,
            "dimension_candidates": dimensions,
            "inferred_date_column": date_column,
            "inferred_period_column": period_column,
            "selected_periods": selected_periods,
        },
    }
    if options.get("reporting_entity_label"):
        recipe["options"]["reporting_entity_label"] = str(
            options["reporting_entity_label"]
        )
    return recipe


def prepare_canonical_frame(
    frame: pl.DataFrame, recipe: dict[str, Any]
) -> pl.DataFrame:
    """Return the canonical frame consumed by the legacy distribution adapter."""

    mappings = recipe["mappings"]
    metric_column = str(mappings["metric_column"])
    date_column = mappings["date_column"]
    period_column = mappings["period_column"]
    raw_columns = frame.collect_schema().names()
    dimensions = [
        str(item)
        for item in mappings.get("dimensions") or []
        if item and str(item) in raw_columns
    ]
    base_dimensions = list(
        dict.fromkeys(
            [
                *dimensions,
                *[
                    dimension
                    for dimension in recipe_cohort_source_dimensions(recipe)
                    if dimension in raw_columns
                ],
            ]
        )
    )
    selected_periods = [
        str(item)
        for item in (recipe.get("options") or {}).get("selected_periods") or []
        if item
    ]
    expressions: list[pl.Expr] = [pl.col(metric_column).cast(pl.Float64)]
    if date_column and str(date_column) in raw_columns:
        expressions.append(
            _parse_date_expression(str(date_column)).alias(CANONICAL_DATE)
        )
    else:
        expressions.append(pl.lit(DEFAULT_DATE).cast(pl.Date).alias(CANONICAL_DATE))
    if period_column and str(period_column) in raw_columns:
        expressions.append(
            pl.col(str(period_column)).cast(pl.Utf8).alias(CANONICAL_PERIOD)
        )
    else:
        expressions.append(pl.lit(CURRENT_PERIOD).alias(CANONICAL_PERIOD))
    expressions.extend(
        pl.col(column).cast(pl.Utf8).alias(column) for column in base_dimensions
    )
    canonical = frame.select(expressions).drop_nulls(subset=[metric_column])
    if not period_column and date_column and str(date_column) in raw_columns:
        canonical = _apply_date_period_plan(
            canonical, (recipe.get("options") or {}).get("period_bucketing_audit") or {}
        )
    if selected_periods:
        canonical = canonical.filter(pl.col(CANONICAL_PERIOD).is_in(selected_periods))
    if get_row_count(canonical) < 3:
        raise ValueError("Distribution charts require at least three non-null rows.")
    return canonical


def _normalize_chart_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def build_chart_specs(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Return standard and small-multiple legacy distribution chart specs."""

    mappings = recipe["mappings"]
    options = recipe["options"]
    requested = [
        _normalize_chart_name(str(item))
        for item in options.get("charts") or list(SUPPORTED_DISTRIBUTION_CHARTS)
    ]
    metric = str(mappings["metric_column"])
    distribution_dimension = mappings.get("distribution_dimension")
    small_multiples_dimension = mappings.get("small_multiples_dimension")
    selected_periods = [str(item) for item in options.get("selected_periods") or []]
    reporting_entity_label = reporting_entity_label_from_recipe(recipe)
    reporting_subject_label = reporting_subject_label_from_recipe(recipe)
    specs: list[dict[str, Any]] = []
    small_multiples_index_cols = [
        column
        for column in [small_multiples_dimension, distribution_dimension]
        if column
    ]
    small_multiples_index_cols = list(dict.fromkeys(small_multiples_index_cols))
    for chart_name in requested:
        if chart_name not in SUPPORTED_DISTRIBUTION_CHARTS:
            raise ValueError(f"Unsupported distribution chart: {chart_name}")
        legacy = SUPPORTED_DISTRIBUTION_CHARTS[chart_name]
        common = {
            "base_chart": chart_name,
            "legacy_chart_key": legacy["legacy_chart_key"],
            "plotter": legacy["plotter"],
            "metric": metric,
            "distribution_dimension": distribution_dimension,
            "selected_periods": selected_periods,
            "reporting_entity_label": reporting_entity_label,
            "reporting_subject_label": reporting_subject_label,
            "max_items": int(options.get("max_chart_items") or 8),
            "aggregate_other_items": bool(options.get("aggregate_other_items", True)),
            "cumulative_histogram": bool(options.get("cumulative_histogram", False)),
            "reversed_ecdf": bool(options.get("reversed_ecdf", False)),
            "show_outliers": bool(options.get("show_outliers", True)),
            "log_x_axis": bool(options.get("log_x_axis", False)),
            "capture_chart_data": True,
        }
        specs.append(
            {
                **common,
                "name": chart_name,
                "artifact_name": legacy["artifact"],
                "index_cols": [],
                "capture_figure": "first",
            }
        )
        if options.get("small_multiples", True) and small_multiples_dimension:
            specs.append(
                {
                    **common,
                    "name": f"{chart_name}_small_multiples",
                    "artifact_name": (
                        f"{Path(legacy['artifact']).stem}_small_multiples.png"
                    ),
                    "small_multiples_dimension": small_multiples_dimension,
                    "small_multiples_max_panels": int(
                        options.get("small_multiples_max_panels")
                        or min(int(options.get("max_chart_items") or 8), 6)
                    ),
                    "index_cols": small_multiples_index_cols,
                    "capture_figure": "last",
                }
            )
    return specs


def _distribution_summary(canonical: pl.DataFrame, metric: str) -> pl.DataFrame:
    return canonical.group_by(CANONICAL_PERIOD).agg(
        pl.len().alias("rows"),
        pl.col(metric).mean().alias("mean"),
        pl.col(metric).median().alias("median"),
        pl.col(metric).std().alias("std"),
        pl.col(metric).min().alias("min"),
        pl.col(metric).max().alias("max"),
    )


def _summary_markdown(
    recipe: dict[str, Any],
    chart_audits: list[dict[str, Any]],
    summary_frame: pl.DataFrame,
) -> str:
    metric = recipe["mappings"]["metric_column"]
    written = [
        audit for audit in chart_audits if audit.get("status") == "written_legacy"
    ]
    data_only = [
        audit for audit in chart_audits if audit.get("status") == "data_written"
    ]
    failed = [
        audit
        for audit in chart_audits
        if audit.get("status") not in {"written_legacy", "data_written"}
    ]
    lines = [
        "# Distribution Analysis",
        "",
        f"Metric: `{metric}`",
        f"Distribution dimension: `{recipe['mappings'].get('distribution_dimension')}`",
        f"Small multiples: `{recipe['mappings'].get('small_multiples_dimension')}`",
        f"Legacy charts written: {len(written)} of {len(chart_audits)}",
        f"Chart data candidates: {len(data_only)}",
        "",
        "## Summary by Period",
        "",
        summary_frame.write_csv().strip(),
    ]
    if failed:
        lines.extend(
            [
                "",
                "## Legacy Failures",
                "",
                *[
                    f"- `{audit.get('chart')}`: {audit.get('error') or audit.get('status')}"
                    for audit in failed
                ],
            ]
        )
    return "\n".join(lines) + "\n"


def _write_xlsx(path: Path, sheets: dict[str, pl.DataFrame]) -> None:
    """Write a simple XLSX workbook using Polars' workbook writer."""

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook: Any | None = None
    for sheet_name, frame in sheets.items():
        workbook = frame.write_excel(
            workbook=path if workbook is None else workbook,
            worksheet=sheet_name[:31],
        )
    if workbook is not None and not bool(getattr(workbook, "fileclosed", False)):
        workbook.close()


def _distribution_chart_base(artifact_id: str) -> str:
    """Return the base distribution chart name for standard and faceted artifacts."""

    suffix = "_small_multiples"
    return artifact_id[: -len(suffix)] if artifact_id.endswith(suffix) else artifact_id


def _normalize_artifact_mode(artifact_mode: str) -> str:
    """Return a supported artifact mode or raise for invalid contract input."""

    normalized = str(artifact_mode or ARTIFACT_MODE_DATA_AND_RENDER).strip().lower()
    if normalized not in ARTIFACT_MODES:
        allowed = ", ".join(sorted(ARTIFACT_MODES))
        raise ValueError(f"Unsupported artifact_mode {artifact_mode!r}; use {allowed}.")
    return normalized


def _chart_artifact_id(spec: dict[str, Any]) -> str:
    """Return the chart artifact ID for generated chart data."""

    artifact_stem = Path(str(spec.get("artifact_name") or "")).stem
    if artifact_stem.endswith("_small_multiples"):
        return artifact_stem
    return str(spec.get("name") or artifact_stem)


def _spec_for_data_only_artifacts(spec: dict[str, Any]) -> dict[str, Any]:
    """Force chart-data capture for data-only artifact generation."""

    return {**spec, "capture_chart_data": True}


def _slim_data_only_context(chart_context: dict[str, Any]) -> dict[str, Any]:
    """Remove render-heavy payloads from data-only chart context."""

    return {
        key: value
        for key, value in chart_context.items()
        if key not in {"plotly_figures", "exports"}
    }


def write_chart_context_artifacts(
    chart_name: str,
    chart_context: dict[str, Any],
    output_dir: Path,
) -> tuple[list[str], dict[str, Any]]:
    """Write per-chart structured data sidecars."""

    context_path = output_dir / f"{chart_name}_chart_context.json"
    write_json(context_path, chart_context)
    paths = [str(context_path)]
    table_path = output_dir / f"{chart_name}_chart_data.csv"
    data_frame = chart_context.get("data_frame")
    table_status = "not_written_no_rows"
    if isinstance(data_frame, dict):
        rows = data_frame.get("rows")
        columns = data_frame.get("columns")
        if isinstance(rows, list) and rows:
            pl.DataFrame(rows, infer_schema_length=None).write_csv(table_path)
            paths.append(str(table_path))
            table_status = "written"
        elif isinstance(columns, list) and columns:
            pl.DataFrame({str(column): [] for column in columns}).write_csv(table_path)
            paths.append(str(table_path))
            table_status = "written_empty"
    return paths, {
        "status": "written",
        "context_path": context_path.name,
        "table_path": table_path.name if table_path.exists() else None,
        "table_status": table_status,
        "source": chart_context.get("chart_data_source"),
    }


def inspect_distribution_inputs(
    input_file: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
    currency: str | None = None,
) -> dict[str, Any]:
    """Inspect inputs and write a suggested recipe."""

    output_dir.mkdir(parents=True, exist_ok=True)
    frame = read_table(input_file)
    existing_recipe = read_json(recipe_path)
    recipe = build_recipe(
        input_file,
        frame,
        language=language,
        currency=currency,
        existing_recipe=existing_recipe,
    )
    inspection = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "distribution-analysis",
        "input_file": str(input_file),
        "created_at": utc_now(),
        "available_analysis_context": available_analysis_context(frame),
        "inspection": recipe["inspection"],
        "suggested_recipe": recipe,
    }
    write_json(output_dir / "distribution_inspection.json", inspection)
    write_json(output_dir / "suggested_recipe.json", recipe)
    return inspection


def run_distribution(
    input_file: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
    currency: str | None = None,
    artifact_mode: str = ARTIFACT_MODE_DATA_AND_RENDER,
) -> DistributionRunResult:
    """Run legacy distribution charts and write outputs."""

    artifact_mode = _normalize_artifact_mode(artifact_mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = read_table(input_file)
    existing_recipe = read_json(recipe_path)
    recipe = build_recipe(
        input_file,
        frame,
        language=language,
        currency=currency,
        existing_recipe=existing_recipe,
    )
    recipe = preserve_recipe_filters(recipe, existing_recipe)
    recipe = preserve_recipe_cohorts(recipe, existing_recipe)
    frame, filter_audit = apply_recipe_filters(frame, recipe)
    recipe.setdefault("options", {})["recipe_filter_audit"] = filter_audit
    run_intake = write_run_intake(
        output_dir,
        input_file,
        recipe_path=recipe_path,
        recipe=recipe,
        source_row_count=frame.height,
    )
    canonical = prepare_canonical_frame(frame, recipe)
    selected_periods = [
        str(item)
        for item in (recipe.get("options") or {}).get("selected_periods") or []
        if item
    ]
    default_previous_period = (
        selected_periods[0] if len(selected_periods) >= 2 else "PY"
    )
    default_current_period = (
        selected_periods[-1] if len(selected_periods) >= 2 else CURRENT_PERIOD
    )
    current_period, previous_period = recipe_cohort_period_labels(
        recipe,
        default_current=default_current_period,
        default_previous=default_previous_period,
    )
    canonical, cohort_audit = apply_recipe_cohorts(
        canonical,
        recipe,
        period_column=CANONICAL_PERIOD,
        value_column=str(recipe["mappings"]["metric_column"]),
        current_period=current_period,
        previous_period=previous_period,
    )
    canonical_path = output_dir / "distribution_canonical.csv"
    canonical.write_csv(canonical_path)
    prepared_manifest_path = write_prepared_data_manifest(
        output_dir=output_dir,
        plugin="distribution-analysis",
        chart_family="distribution",
        source_file=input_file,
        prepared_path=canonical_path,
        frame=canonical,
        recipe=recipe,
        preparation_audit={
            "status": "prepared",
            "recipe_filters": filter_audit,
            "recipe_cohorts": cohort_audit,
        },
    )
    used_recipe_path = output_dir / "used_recipe.json"
    write_json(used_recipe_path, recipe)

    chart_specs = build_chart_specs(recipe)
    cache = LegacyPreparedDataCache.empty()
    render_charts = artifact_mode != ARTIFACT_MODE_DATA_ONLY
    chart_audits: list[dict[str, Any]] = []
    chart_contexts: list[dict[str, Any]] = []
    chart_context_artifacts: dict[str, Any] = {}
    artifact_paths: list[str] = [
        str(canonical_path),
        str(prepared_manifest_path),
        str(used_recipe_path),
    ]
    try:
        for spec in chart_specs:
            run_spec = (
                _spec_for_data_only_artifacts(spec)
                if artifact_mode == ARTIFACT_MODE_DATA_ONLY
                else spec
            )
            export = write_legacy_distribution_chart(
                canonical,
                recipe,
                output_dir,
                run_spec,
                prepared_data_cache=cache,
                render=render_charts,
            )
            chart_audits.append(export.audit)
            artifact_paths.extend(export.paths)
            if export.chart_context is not None:
                chart_context = export.chart_context
                if artifact_mode == ARTIFACT_MODE_DATA_ONLY:
                    chart_context = _slim_data_only_context(chart_context)
                context_paths, context_audit = write_chart_context_artifacts(
                    str(spec["name"]),
                    chart_context,
                    output_dir,
                )
                artifact_paths.extend(context_paths)
                chart_context_artifacts[str(spec["name"])] = context_audit
                export.audit["chart_context"] = context_audit
                chart_contexts.append(chart_context)
    finally:
        cleanup_legacy_imports()

    metric = str(recipe["mappings"]["metric_column"])
    summary_frame = _distribution_summary(canonical, metric)
    summary_csv = output_dir / "distribution_summary.csv"
    summary_frame.write_csv(summary_csv)
    artifact_paths.append(str(summary_csv))
    _write_xlsx(
        output_dir / "distribution_results.xlsx",
        {"summary": summary_frame, "canonical": canonical},
    )
    artifact_paths.append(str(output_dir / "distribution_results.xlsx"))
    audit = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "distribution-analysis",
        "created_at": utc_now(),
        "input_file": str(input_file),
        "artifact_mode": artifact_mode,
        "charts_requested": [spec["name"] for spec in chart_specs],
        "charts": chart_audits,
        "prepared_data_cache": cache.audit_delta((0, 0, 0, 0, 0, 0))[
            "prepared_data_cache"
        ],
        "legacy_inventory": {
            "supported_charts": list(SUPPORTED_DISTRIBUTION_CHARTS),
            "small_multiples_mode": "same legacy plotter with smallMultiplesColumn",
        },
        "checks": {
            "legacy_chart_attempt_count": len(chart_audits),
            "legacy_chart_written_count": sum(
                1
                for audit_item in chart_audits
                if audit_item.get("status") == "written_legacy"
            ),
            "legacy_chart_data_count": sum(
                1
                for audit_item in chart_audits
                if audit_item.get("status") in {"written_legacy", "data_written"}
            ),
        },
    }
    context = {
        "schema_version": SCHEMA_VERSION,
        "producer": {"plugin": "distribution-analysis"},
        "artifact_mode": artifact_mode,
        "recipe": recipe,
        "prepared_data_manifest": prepared_manifest_path.name,
        "recipe_filters": filter_audit,
        "recipe_cohorts": cohort_audit,
        "summary": summary_frame.to_dicts(),
        "charts": chart_contexts,
        "chart_context_artifacts": chart_context_artifacts,
        "audit_status": [
            {
                "chart": audit_item.get("chart"),
                "status": audit_item.get("status"),
                "legacy_reference_function": audit_item.get(
                    "legacy_reference_function"
                ),
                "legacy_draw_function": audit_item.get("legacy_draw_function"),
            }
            for audit_item in chart_audits
        ],
    }
    audit_path = output_dir / "distribution_audit.json"
    context_path = output_dir / "distribution_context.json"
    write_json(audit_path, audit)
    write_json(context_path, context)
    artifact_paths.extend([str(audit_path), str(context_path)])
    summary_markdown = _summary_markdown(recipe, chart_audits, summary_frame)
    summary_path = output_dir / "distribution_summary.md"
    summary_path.write_text(summary_markdown, encoding="utf-8")
    artifact_paths.append(str(summary_path))
    report_path = output_dir / "distribution_client_report.md"
    report_path.write_text(summary_markdown, encoding="utf-8")
    artifact_paths.append(str(report_path))
    write_json(audit_path, audit)
    review_session = write_review_session_artifacts(
        output_dir,
        input_file,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        recipe_path=recipe_path,
        recipe=recipe,
        summary_rows=summary_frame.to_dicts(),
        audit=audit,
    )
    audit["review_session"] = {
        "run_intake_path": review_session.run_intake_path.name,
        "review_payload_path": review_session.review_payload_path.name,
        "ui_decisions_path": review_session.ui_decisions_path.name,
        "final_artifacts_path": review_session.final_artifacts_path.name,
        "review_item_count": review_session.review_item_count,
    }
    artifact_paths.extend(
        [
            str(review_session.run_intake_path),
            str(review_session.review_payload_path),
            str(review_session.ui_decisions_path),
            str(review_session.final_artifacts_path),
        ]
    )
    write_json(audit_path, audit)

    zip_path = output_dir / "distribution_artifacts.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifact_paths:
            path = Path(artifact)
            if path.exists() and path.is_file():
                archive.write(path, path.relative_to(output_dir))
    artifact_paths.append(str(zip_path))
    return DistributionRunResult(
        canonical_frame=canonical,
        audit=audit,
        summary_markdown=summary_markdown,
        artifact_paths=artifact_paths,
    )
