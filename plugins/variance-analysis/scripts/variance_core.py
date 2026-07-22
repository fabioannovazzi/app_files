"""Deterministic variance analysis helpers for the Codex plugin."""

from __future__ import annotations

import argparse
import calendar
import itertools
import json
import logging
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import polars as pl
from ibcs_titles import build_ibcs_title
from legacy_adapter import (
    cleanup_legacy_imports,
    legacy_date_period_context,
    run_legacy_variable_dimension_bridge,
    run_legacy_variable_dimension_component_bridge,
    run_legacy_variance,
)
from legacy_plotting import write_pvm_decomposition_ladder_png, write_waterfall_png

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
from exploded_variance_bridge_chart import (
    DEFAULT_CHILD_TOP_N as EXPLODED_BRIDGE_DEFAULT_CHILD_TOP_N,
)
from exploded_variance_bridge_chart import (
    DEFAULT_MAX_DRILLDOWNS as EXPLODED_BRIDGE_DEFAULT_MAX_DRILLDOWNS,
)
from exploded_variance_bridge_chart import (
    write_exploded_variance_bridge_artifacts,
)
from review_session import write_review_session_artifacts, write_run_intake
from root_cause_bridge_chart import write_root_cause_bridge_png
from root_cause_client_report import write_root_cause_client_report
from total_by_dimension_bridge_chart import (
    DEFAULT_TOP_N as TOTAL_BY_DIMENSION_DEFAULT_TOP_N,
)
from total_by_dimension_bridge_chart import (
    write_total_by_dimension_bridge_artifacts,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PLUGIN_ROOT / "vendor"
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_VENDOR_ROOT = REPO_ROOT / "plugins" / "_shared" / "vendor"


def _ensure_shared_modules_path() -> None:
    """Make shared plugin harness modules importable in repo and ZIP runs."""

    shared_parent = SHARED_VENDOR_ROOT if SHARED_VENDOR_ROOT.exists() else VENDOR_ROOT
    shared_text = str(shared_parent)
    if shared_text in sys.path:
        sys.path.remove(shared_text)
    sys.path.insert(0, shared_text)
    module_root = (shared_parent / "modules").resolve()
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            if not module_file or not Path(module_file).resolve().is_relative_to(
                module_root
            ):
                del sys.modules[name]


_ensure_shared_modules_path()
from modules.chart_harness import (  # noqa: E402  # isort: skip
    apply_recipe_filters,
    apply_recipe_cohorts,
    available_analysis_context,
    default_scenario_comparison_pair,
    PERIOD_GRAIN_MONTH,
    PERIOD_GRAIN_QUARTER,
    PERIOD_GRAIN_WEEK,
    PERIOD_GRAIN_YEAR,
    PERIOD_TYPE_CUSTOM,
    PERIOD_TYPE_FISCAL,
    PERIOD_TYPE_ROLLING,
    PERIOD_TYPE_TO_DATE,
    period_contract_options,
    preserve_recipe_cohorts,
    preserve_recipe_filters,
    recipe_cohort_dimension_names,
    recipe_cohort_source_dimensions,
    scenario_column_kind,
    write_prepared_data_manifest,
)

__all__ = [
    "InspectionResult",
    "VarianceRunResult",
    "add_common_args",
    "configure_logging",
    "inspect_variance_inputs",
    "run_variance_analysis",
]

LOGGER = logging.getLogger(__name__)
LEGACY_RENDER_ERRORS = (
    AttributeError,
    IndexError,
    ImportError,
    KeyError,
    ModuleNotFoundError,
    NameError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    pl.exceptions.PolarsError,
)
SCHEMA_VERSION = "1.0"
ARTIFACT_MODE_DATA_ONLY = "data_only"
ARTIFACT_MODE_DATA_AND_RENDER = "data_and_render"
ARTIFACT_MODES = {
    ARTIFACT_MODE_DATA_ONLY,
    ARTIFACT_MODE_DATA_AND_RENDER,
}
VARIANCE_CHART_STANDARD_WATERFALL = "standard_variance_waterfall"
VARIANCE_CHART_PVM_LADDER = "pvm_decomposition_ladder"
VARIANCE_CHART_SMALL_MULTIPLES = "standard_variance_small_multiples"
VARIANCE_CHART_TOTAL_BY_DIMENSION = "total_by_dimension_bridge"
VARIANCE_CHART_EXPLODED_BRIDGE = "exploded_variance_bridge"
VARIANCE_CHART_ROOT_CAUSE = "root_cause_total_bridge"
TOTAL_DIMENSION = "__total"
ROOT_CAUSE_BRIDGE_MEASURE_COLUMNS = {
    "bridge_level",
    "bridge_dimensions",
    "variance_type",
    "variance_amount",
    "amount_baseline",
    "amount_comparison",
    "units_baseline",
    "units_comparison",
    "bridge_unique_value_weight",
}
ROOT_CAUSE_AUTO_DRILLDOWN_VALUES = {
    "none",
    "single_row",
    "dominant_row",
    "all_selected",
}
COMPARISON_BASIS_SCENARIO = "scenario"
COMPARISON_BASIS_PERIOD = "period"
COMPARISON_BASIS_VALUES = {COMPARISON_BASIS_SCENARIO, COMPARISON_BASIS_PERIOD}
PERIOD_MODE_NOT_APPLICABLE = "not_applicable"
PERIOD_MODE_CALENDAR = "calendar_period"
PERIOD_MODE_YEAR_TO_DATE = "year_to_date"
PERIOD_MODE_ROLLING = "rolling_period"
PERIOD_MODE_CUSTOM = "custom"
PERIOD_COMPARISON_MODE_VALUES = {
    PERIOD_MODE_NOT_APPLICABLE,
    PERIOD_MODE_CALENDAR,
    PERIOD_MODE_YEAR_TO_DATE,
    PERIOD_MODE_ROLLING,
    PERIOD_MODE_CUSTOM,
}
SYNTHETIC_PERIOD_COLUMN = "__variance_period_bucket"
DATE_WORK_COLUMN = "__variance_date"
ROLLING_COMPARISON_PRIOR_YEAR = "prior_year"
ROLLING_COMPARISON_PREVIOUS_WINDOW = "previous_window"
ROLLING_COMPARISON_VALUES = {
    ROLLING_COMPARISON_PRIOR_YEAR,
    ROLLING_COMPARISON_PREVIOUS_WINDOW,
}
DATE_COLUMN_HINTS = (
    "date",
    "order date",
    "orderdate",
    "sales date",
    "invoice date",
    "transaction date",
    "posting date",
)
DIMENSION_NAME_PRIORITY = (
    "category",
    "subcategory",
    "productline",
    "product line",
    "region",
    "country",
    "group",
    "segment",
    "channel",
    "brand",
    "product",
    "productname",
    "product name",
    "customer segment",
)
SMALL_MULTIPLES_DIMENSION_NAME_PRIORITY = (
    "productline",
    "product line",
    "category",
    "subcategory",
    "region",
    "country",
    "market",
    "territory",
    "group",
    "segment",
    "customer segment",
    "channel",
    "brand",
    "product",
    "customer",
    "productname",
    "product name",
)
SMALL_MULTIPLES_GRANULAR_NAME_HINTS = (
    "sku",
    "item",
    "productname",
    "product name",
    "customer",
    "customer name",
    "account",
    "id",
    "code",
    "number",
)
SMALL_MULTIPLES_MAX_REASONABLE_CARDINALITY = 50
SMALL_MULTIPLES_IDEAL_CARDINALITY = 12
SMALL_MULTIPLES_MIN_DIMENSION_SCORE = 30.0
SMALL_MULTIPLES_PANEL_LIMIT = 12
SMALL_MULTIPLES_NULL_LABEL = "N/A"
SMALL_MULTIPLES_OTHER_LABEL = "Others aggregated"
SMALL_MULTIPLES_WORK_COLUMN = "__small_multiples_dimension_value"
TOTAL_BY_DIMENSION_MIN_SCORE = 10.0
TOTAL_BY_DIMENSION_MAX_REASONABLE_CARDINALITY = 250
TOTAL_BY_DIMENSION_NAME_PRIORITY = (
    "company",
    "brand",
    "region",
    "market",
    "country",
    "channel",
    "customer segment",
    "segment",
    "category",
    "subcategory",
    "productline",
    "product line",
    "retailer",
)
STANDARD_VARIANCE_COMPONENT_COLUMNS = (
    ("Price", "price_variance"),
    ("volume_or_units", "volume_variance"),
    ("Mix", "mix_variance"),
)
TOLERANCE = 1e-9
CALCULATION_GRAIN_NAME_PRIORITY = (
    "sku",
    "item",
    "product",
    "productname",
    "product name",
    "customer",
    "customer name",
    "account",
)

COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "period_column": (
        "period",
        "month",
        "year",
        "fiscal period",
        "date",
        "time",
    ),
    "amount_column": (
        "sales",
        "revenue",
        "turnover",
        "amount",
        "net sales",
        "value",
    ),
    "units_column": (
        "units",
        "unit",
        "qty",
        "quantity",
        "volume",
        "pieces",
    ),
    "discount_column": (
        "discount",
        "rebate",
        "promo",
        "markdown",
    ),
    "cogs_column": (
        "cogs",
        "cost of goods",
        "cost",
        "costs",
        "unit cost",
    ),
}


@dataclass(frozen=True)
class InspectionResult:
    """Inspection payload and suggested recipe."""

    payload: dict[str, Any]
    recipe: dict[str, Any]


@dataclass(frozen=True)
class VarianceRunResult:
    """Variance output payloads returned after a deterministic run."""

    frame: pl.DataFrame
    audit: dict[str, Any]
    summary_markdown: str
    artifact_paths: list[str]


def configure_logging(verbose: bool = False) -> None:
    """Configure CLI logging."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common plugin CLI arguments."""

    parser.add_argument(
        "--language",
        default="en",
        choices=["it", "en", "fr", "de", "es"],
        help="Working/output language for Codex-facing summaries.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show debug logging.",
    )
    parser.add_argument(
        "--artifact-mode",
        choices=sorted(ARTIFACT_MODES),
        default=ARTIFACT_MODE_DATA_AND_RENDER,
        help=("Write chart data only or keep the legacy data-and-render behavior."),
    )


def utc_now() -> str:
    """Return an ISO timestamp for audit outputs."""

    return datetime.now(timezone.utc).isoformat()


def get_schema_and_column_names(df: pl.DataFrame) -> tuple[list[str], dict[str, str]]:
    """Return column names and JSON-safe schema."""

    return list(df.schema.keys()), {
        name: str(dtype) for name, dtype in df.schema.items()
    }


def _collect_csv_scan(path: Path, *, separator: str) -> pl.DataFrame:
    """Read delimited input through a lazy scan and collect once."""

    lf = pl.scan_csv(path, separator=separator, infer_schema_length=10000)
    try:
        return lf.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return lf.collect()


def read_table(path: Path) -> pl.DataFrame:
    """Read a supported CSV or Excel file."""

    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ".tsv", ".psv"}:
        separator = {
            ".tsv": "\t",
            ".psv": "|",
        }.get(suffix, ",")
        return _collect_csv_scan(path, separator=separator)
    if suffix in {".xlsx", ".xlsm"}:
        return pl.read_excel(path)
    raise ValueError(
        f"Unsupported input file type '{suffix}'. Use CSV, TSV, PSV, XLSX, or XLSM."
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a stable JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def warn_if_output_dir_has_existing_files(output_dir: Path, context: str) -> None:
    """Log a warning when a run may mix with stale output files."""

    if not output_dir.exists() or not output_dir.is_dir():
        return
    existing_files = sorted(
        path.name for path in output_dir.iterdir() if path.is_file()
    )
    if not existing_files:
        return
    visible_files = ", ".join(existing_files[:8])
    if len(existing_files) > 8:
        visible_files = f"{visible_files}, ..."
    LOGGER.warning(
        "%s output directory already contains files; this run may overwrite "
        "matching artifacts and leave unrelated stale artifacts in place: %s "
        "(existing files: %s)",
        context,
        output_dir,
        visible_files,
    )


def json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation of common analysis values."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date, Path)):
        return str(value)
    return value


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in recipe: {path}")
    return payload


def normalize_name(name: str) -> str:
    """Normalize a column name for deterministic matching."""

    return " ".join(name.replace("_", " ").replace("-", " ").lower().split())


def compact_normalized_name(name: str) -> str:
    """Return a compact normalized name for underscore/spacing-insensitive matching."""

    return "".join(token for token in normalize_name(name).split())


def first_matching_column(columns: Iterable[str], hints: Iterable[str]) -> str | None:
    """Return the first column whose normalized name matches the hints."""

    normalized_columns = [(column, normalize_name(column)) for column in columns]
    normalized_hints = [normalize_name(hint) for hint in hints]
    for hint in normalized_hints:
        for column, normalized in normalized_columns:
            if normalized == hint:
                return column
    for hint in normalized_hints:
        for column, normalized in normalized_columns:
            if hint in normalized:
                return column
    return None


def is_numeric_dtype(dtype: pl.DataType) -> bool:
    """Return whether a Polars dtype is numeric enough for variance math."""

    return dtype.is_numeric()


def is_temporal_dtype(dtype: pl.DataType) -> bool:
    """Return whether a Polars dtype is temporal."""

    return dtype.is_temporal()


def suggested_date_column(df: pl.DataFrame, columns: list[str]) -> str | None:
    """Return the best date column for rolling/YTD bucket preparation."""

    hinted = first_matching_column(columns, DATE_COLUMN_HINTS)
    if hinted and is_temporal_dtype(df.schema[hinted]):
        return hinted
    temporal_columns = [
        column for column in columns if is_temporal_dtype(df.schema[column])
    ]
    if hinted:
        return hinted
    return temporal_columns[0] if temporal_columns else None


def distinct_text_values(df: pl.DataFrame, column: str) -> list[str]:
    """Return distinct non-empty text values preserving source labels."""

    values = (
        df.select(pl.col(column).cast(pl.Utf8).drop_nulls().unique().sort())
        .to_series(0)
        .to_list()
    )
    return [str(value).strip() for value in values if str(value).strip()]


def is_scenario_comparison_column(df: pl.DataFrame, column: str | None) -> bool:
    """Return whether a column contains an AC-vs-plan-like scenario comparison.

    This deterministic rule is limited to exact IBCS scenario roles: Actual can
    be compared with Plan, Forecast, or Budget. AC/PY alone remains a period
    comparison, not a scenario comparison.
    """

    if not column or column not in df.schema:
        return False
    values = distinct_text_values(df, column)
    if scenario_column_kind(column, values) != COMPARISON_BASIS_SCENARIO:
        return False
    baseline, comparison = default_scenario_comparison_pair(values)
    return bool(baseline and comparison)


def is_plan_actual_scenario_column(df: pl.DataFrame, column: str | None) -> bool:
    """Return whether a column is a supported Actual-vs-scenario code column."""

    return is_scenario_comparison_column(df, column)


def plan_actual_scenario_column(df: pl.DataFrame, columns: Iterable[str]) -> str | None:
    """Return the AC-vs-plan/forecast/budget scenario column when present."""

    for column in columns:
        if is_plan_actual_scenario_column(df, column):
            return column
    return None


def ranked_dimension_candidates(candidates: list[str]) -> list[str]:
    """Return dimension candidates with known business dimensions first."""

    selected: list[str] = []
    normalized = [(column, normalize_name(column)) for column in candidates]
    for hint in DIMENSION_NAME_PRIORITY:
        normalized_hint = normalize_name(hint)
        for column, normalized_name in normalized:
            if normalized_name == normalized_hint and column not in selected:
                selected.append(column)
    selected.extend(column for column in candidates if column not in selected)
    return selected


def dimension_priority_score(column: str, priority: tuple[str, ...]) -> float:
    """Return a deterministic business-readability score for a dimension name."""

    normalized_name = normalize_name(column)
    compact_name = compact_normalized_name(column)
    for index, hint in enumerate(priority):
        normalized_hint = normalize_name(hint)
        compact_hint = compact_normalized_name(hint)
        base_score = max(12.0, 55.0 - (index * 3.0))
        if normalized_name == normalized_hint or compact_name == compact_hint:
            return base_score
        if compact_hint in compact_name or compact_name in compact_hint:
            return max(10.0, base_score - 8.0)
    return 8.0


def name_contains_hint(column: str, hint: str) -> bool:
    """Return whether a normalized column name contains a safe name hint."""

    normalized_name = normalize_name(column)
    normalized_hint = normalize_name(hint)
    compact_hint = compact_normalized_name(hint)
    if len(compact_hint) <= 2:
        return normalized_hint in normalized_name.split()
    if normalized_hint in normalized_name:
        return True
    return compact_hint in compact_normalized_name(column)


def cardinality_score(cardinality: int) -> float:
    """Return a small-multiples score for the number of panels needed."""

    if cardinality < 2:
        return -100.0
    if cardinality <= 4:
        return 26.0
    if cardinality <= SMALL_MULTIPLES_IDEAL_CARDINALITY:
        return 32.0
    if cardinality <= 24:
        return 16.0
    if cardinality <= SMALL_MULTIPLES_MAX_REASONABLE_CARDINALITY:
        return 4.0
    return -25.0


def granularity_penalty(column: str, cardinality: int) -> float:
    """Return penalty for columns that usually create noisy small multiples."""

    normalized_name = normalize_name(column)
    penalty = 0.0
    if any(
        name_contains_hint(normalized_name, hint)
        for hint in SMALL_MULTIPLES_GRANULAR_NAME_HINTS
    ):
        penalty += 18.0
    if cardinality > SMALL_MULTIPLES_IDEAL_CARDINALITY:
        penalty += 8.0
    if cardinality > SMALL_MULTIPLES_MAX_REASONABLE_CARDINALITY:
        penalty += 20.0
    return penalty


def select_waterfall_small_multiples_dimension(
    result: pl.DataFrame,
    recipe: dict[str, Any],
) -> dict[str, Any]:
    """Choose a presentation dimension for standard-variance small multiples."""

    options = recipe.get("options") or {}
    mappings = recipe.get("mappings") or {}
    dimensions = [
        str(column)
        for column in mappings.get("dimensions") or []
        if str(column) in result.schema
    ]
    explicit_dimension = options.get("waterfall_small_multiples_dimension")
    if explicit_dimension:
        explicit_dimension = str(explicit_dimension)
        return {
            "status": (
                "selected_explicit"
                if explicit_dimension in result.schema
                else "not_selected_missing_explicit_dimension"
            ),
            "dimension": (
                explicit_dimension if explicit_dimension in result.schema else None
            ),
            "reason": "explicit_recipe_or_cli_dimension",
            "candidates": [],
        }
    if not dimensions:
        return {
            "status": "not_selected_no_mapped_dimensions",
            "dimension": None,
            "reason": "standard_variance_has_no_reporting_dimension",
            "candidates": [],
        }

    candidates: list[dict[str, Any]] = []
    for dimension in dimensions:
        grouped = (
            result.group_by(dimension)
            .agg(pl.col("total_delta").sum().alias("_delta"))
            .with_columns(pl.col("_delta").abs().alias("_abs_delta"))
            .sort("_abs_delta", descending=True)
        )
        cardinality = grouped.height
        total_abs_delta = float(
            grouped.select(pl.col("_abs_delta").sum()).item() or 0.0
        )
        top_abs_delta = float(grouped.select(pl.col("_abs_delta").max()).item() or 0.0)
        non_zero_count = grouped.filter(pl.col("_abs_delta") > 0.000001).height
        top_share = top_abs_delta / total_abs_delta if total_abs_delta else 0.0
        name_score = dimension_priority_score(
            dimension,
            SMALL_MULTIPLES_DIMENSION_NAME_PRIORITY,
        )
        candidate_cardinality_score = cardinality_score(cardinality)
        spread_score = min(14.0, float(non_zero_count) * 2.0)
        if 0.25 <= top_share <= 0.85:
            spread_score += 8.0
        elif top_share > 0.95:
            spread_score -= 4.0
        penalty = granularity_penalty(dimension, cardinality)
        score = name_score + candidate_cardinality_score + spread_score - penalty
        candidates.append(
            {
                "dimension": dimension,
                "score": round(score, 3),
                "name_score": round(name_score, 3),
                "cardinality_score": round(candidate_cardinality_score, 3),
                "spread_score": round(spread_score, 3),
                "granularity_penalty": round(penalty, 3),
                "cardinality": cardinality,
                "non_zero_members": non_zero_count,
                "top_member_share_of_abs_delta": round(top_share, 6),
            }
        )
    candidates.sort(
        key=lambda item: (
            float(item["score"]),
            float(item["name_score"]),
            -int(item["cardinality"]),
        ),
        reverse=True,
    )
    best = candidates[0]
    if float(best["score"]) < SMALL_MULTIPLES_MIN_DIMENSION_SCORE:
        return {
            "status": "not_selected_no_clear_dimension",
            "dimension": None,
            "reason": "no_candidate_met_business_readability_threshold",
            "candidates": candidates,
        }
    return {
        "status": "selected_ranked_candidate",
        "dimension": best["dimension"],
        "reason": (
            "highest score from business-readability, cardinality, and variance "
            "spread heuristic"
        ),
        "candidates": candidates,
    }


def select_total_by_dimension_bridge_dimension(
    result: pl.DataFrame,
    recipe: dict[str, Any],
) -> dict[str, Any]:
    """Choose one fixed dimension for the total variance bridge."""

    options = recipe.get("options") or {}
    mappings = recipe.get("mappings") or {}
    dimensions = [
        str(column)
        for column in mappings.get("dimensions") or []
        if str(column) in result.schema
    ]
    explicit_dimension = options.get("total_by_dimension_bridge_dimension")
    if explicit_dimension:
        explicit_dimension = str(explicit_dimension)
        return {
            "status": (
                "selected_explicit"
                if explicit_dimension in result.schema
                else "not_selected_missing_explicit_dimension"
            ),
            "dimension": (
                explicit_dimension if explicit_dimension in result.schema else None
            ),
            "reason": "explicit_recipe_or_cli_dimension",
            "candidates": [],
        }
    if not dimensions:
        return {
            "status": "not_selected_no_mapped_dimensions",
            "dimension": None,
            "reason": "total_by_dimension_bridge_requires_one_dimension",
            "candidates": [],
        }

    candidates: list[dict[str, Any]] = []
    for dimension in dimensions:
        grouped = (
            result.group_by(dimension)
            .agg(pl.col("total_delta").sum().alias("_delta"))
            .with_columns(pl.col("_delta").abs().alias("_abs_delta"))
            .sort("_abs_delta", descending=True)
        )
        cardinality = grouped.height
        total_abs_delta = float(
            grouped.select(pl.col("_abs_delta").sum()).item() or 0.0
        )
        top_abs_delta = float(grouped.select(pl.col("_abs_delta").max()).item() or 0.0)
        non_zero_count = grouped.filter(pl.col("_abs_delta") > TOLERANCE).height
        top_share = top_abs_delta / total_abs_delta if total_abs_delta else 0.0
        name_score = dimension_priority_score(
            dimension,
            TOTAL_BY_DIMENSION_NAME_PRIORITY,
        )
        if 2 <= cardinality <= 12:
            cardinality_component = 28.0
        elif cardinality <= 36:
            cardinality_component = 18.0
        elif cardinality <= TOTAL_BY_DIMENSION_MAX_REASONABLE_CARDINALITY:
            cardinality_component = 8.0
        else:
            cardinality_component = -20.0
        spread_score = min(16.0, float(non_zero_count) * 2.0)
        if 0.2 <= top_share <= 0.9:
            spread_score += 6.0
        elif top_share > 0.98:
            spread_score -= 6.0
        penalty = granularity_penalty(dimension, cardinality)
        score = name_score + cardinality_component + spread_score - penalty
        candidates.append(
            {
                "dimension": dimension,
                "score": round(score, 3),
                "name_score": round(name_score, 3),
                "cardinality_score": round(cardinality_component, 3),
                "spread_score": round(spread_score, 3),
                "granularity_penalty": round(penalty, 3),
                "cardinality": cardinality,
                "non_zero_members": non_zero_count,
                "top_member_share_of_abs_delta": round(top_share, 6),
            }
        )
    candidates.sort(
        key=lambda item: (
            float(item["score"]),
            float(item["name_score"]),
            -int(item["cardinality"]),
        ),
        reverse=True,
    )
    best = candidates[0]
    if float(best["score"]) < TOTAL_BY_DIMENSION_MIN_SCORE:
        fallback_dimension = dimensions[0]
        return {
            "status": "selected_fallback_first_dimension",
            "dimension": fallback_dimension,
            "reason": "no_candidate_met_threshold_but_single_dimension_view_is_lightweight",
            "candidates": candidates,
        }
    return {
        "status": "selected_ranked_candidate",
        "dimension": best["dimension"],
        "reason": (
            "highest score from business-readability, cardinality, and total "
            "variance spread heuristic"
        ),
        "candidates": candidates,
    }


def select_exploded_variance_bridge_dimensions(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    fallback_parent_dimension: str | None = None,
) -> dict[str, Any]:
    """Choose parent and child dimensions for the exploded bridge."""

    options = recipe.get("options") or {}
    mappings = recipe.get("mappings") or {}
    dimensions = [
        str(column)
        for column in mappings.get("dimensions") or []
        if str(column) in result.schema
    ]
    if len(dimensions) < 2:
        return {
            "status": "not_selected_insufficient_dimensions",
            "parent_dimension": None,
            "child_dimension": None,
            "reason": "exploded_variance_bridge_requires_two_dimensions",
        }

    explicit_parent = options.get("exploded_variance_bridge_parent_dimension")
    parent_dimension = (
        str(explicit_parent)
        if explicit_parent
        else fallback_parent_dimension
        or options.get("total_by_dimension_bridge_dimension")
    )
    if parent_dimension:
        parent_dimension = str(parent_dimension)
        if parent_dimension not in result.schema:
            return {
                "status": "not_selected_missing_parent_dimension",
                "parent_dimension": None,
                "child_dimension": None,
                "reason": "configured_parent_dimension_missing",
            }
    else:
        parent_selection = select_total_by_dimension_bridge_dimension(result, recipe)
        parent_dimension = parent_selection.get("dimension")
        if not parent_dimension:
            return {
                "status": "not_selected_no_parent_dimension",
                "parent_dimension": None,
                "child_dimension": None,
                "reason": parent_selection.get("reason"),
                "parent_selection": parent_selection,
            }

    explicit_child = options.get("exploded_variance_bridge_child_dimension")
    if explicit_child:
        child_dimension = str(explicit_child)
        if child_dimension not in result.schema:
            return {
                "status": "not_selected_missing_child_dimension",
                "parent_dimension": parent_dimension,
                "child_dimension": None,
                "reason": "configured_child_dimension_missing",
            }
        if child_dimension == parent_dimension:
            return {
                "status": "not_selected_child_matches_parent",
                "parent_dimension": parent_dimension,
                "child_dimension": None,
                "reason": "parent_and_child_dimensions_must_differ",
            }
        return {
            "status": "selected_explicit",
            "parent_dimension": parent_dimension,
            "child_dimension": child_dimension,
            "reason": "explicit_recipe_or_cli_dimensions",
        }

    for dimension in dimensions:
        if dimension != parent_dimension:
            return {
                "status": "selected_parent_plus_next_dimension",
                "parent_dimension": parent_dimension,
                "child_dimension": dimension,
                "reason": "parent_dimension_plus_first_other_mapped_dimension",
            }
    return {
        "status": "not_selected_no_child_dimension",
        "parent_dimension": parent_dimension,
        "child_dimension": None,
        "reason": "no_mapped_dimension_remaining_after_parent",
    }


def _numeric_column_sum(frame: pl.DataFrame, column: str) -> float:
    """Return a stable numeric sum for a result column that may be absent."""

    if frame.is_empty() or column not in frame.schema:
        return 0.0
    value = frame.select(pl.col(column).sum()).item()
    return float(value or 0.0)


def standard_variance_component_columns(
    recipe: dict[str, Any],
) -> list[tuple[str, str]]:
    """Return standard variance components using the same labels as charts."""

    volume_label = "Units" if recipe["mappings"].get("units_column") else "Volume"
    return [
        (volume_label if label == "volume_or_units" else label, column)
        for label, column in STANDARD_VARIANCE_COMPONENT_COLUMNS
    ]


def _small_multiples_panel_slices(
    result: pl.DataFrame,
    dimension: str,
    *,
    limit: int = SMALL_MULTIPLES_PANEL_LIMIT,
) -> tuple[pl.DataFrame, list[dict[str, Any]], bool]:
    """Return chart-aligned panel filters, including an Other member panel."""

    working = result.with_columns(
        pl.col(dimension)
        .cast(pl.Utf8)
        .fill_null(SMALL_MULTIPLES_NULL_LABEL)
        .alias(SMALL_MULTIPLES_WORK_COLUMN)
    )
    ranked = (
        working.group_by(SMALL_MULTIPLES_WORK_COLUMN)
        .agg(pl.col("total_delta").abs().sum().alias("_abs_delta"))
        .sort("_abs_delta", descending=True)
    )
    all_values = [str(value) for value in ranked[SMALL_MULTIPLES_WORK_COLUMN].to_list()]
    selected_values = all_values[:limit]
    include_other = len(all_values) > limit
    if include_other:
        selected_values = all_values[: max(1, limit - 1)]

    panels = [
        {
            "panel_number": index + 1,
            "dimension_value": value,
            "panel_type": "member",
            "selected_values": [value],
        }
        for index, value in enumerate(selected_values)
    ]
    if include_other:
        panels.append(
            {
                "panel_number": len(panels) + 1,
                "dimension_value": SMALL_MULTIPLES_OTHER_LABEL,
                "panel_type": "other_members",
                "selected_values": [
                    value for value in all_values if value not in selected_values
                ],
            }
        )
    return working, panels, include_other


def _small_multiples_panel_frame(
    working: pl.DataFrame,
    panel: dict[str, Any],
) -> pl.DataFrame:
    """Return the result rows included in one small-multiples panel."""

    selected_values = [str(value) for value in panel["selected_values"]]
    if panel["panel_type"] == "other_members":
        return working.filter(
            pl.col(SMALL_MULTIPLES_WORK_COLUMN).is_in(selected_values)
        )
    return working.filter(pl.col(SMALL_MULTIPLES_WORK_COLUMN) == selected_values[0])


def _panel_component_values(
    panel_frame: pl.DataFrame,
    recipe: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Return component rows and aggregate totals for one panel."""

    amount_baseline = _numeric_column_sum(panel_frame, "amount_baseline")
    amount_comparison = _numeric_column_sum(panel_frame, "amount_comparison")
    total_delta = _numeric_column_sum(panel_frame, "total_delta")
    if recipe["mappings"].get("units_column"):
        unit_mix_label = "Units & mix"
        components = [
            {
                "variance_type": "Price",
                "variance_amount": _numeric_column_sum(panel_frame, "price_variance"),
                "is_residual_other": False,
                "is_residual_balance": False,
                "displayed_in_chart": True,
            },
            {
                "variance_type": unit_mix_label,
                "variance_amount": _numeric_column_sum(panel_frame, "volume_variance")
                + _numeric_column_sum(panel_frame, "mix_variance"),
                "is_residual_other": False,
                "is_residual_balance": False,
                "displayed_in_chart": True,
            },
        ]
    else:
        components = [
            {
                "variance_type": "Total variance",
                "variance_amount": total_delta,
                "is_residual_other": False,
                "is_residual_balance": False,
                "displayed_in_chart": True,
            }
        ]
    component_sum = sum(item["variance_amount"] for item in components)
    residual = total_delta - component_sum
    components.append(
        {
            "variance_type": "Balance",
            "variance_amount": residual,
            "is_residual_other": True,
            "is_residual_balance": True,
            "displayed_in_chart": abs(residual) > TOLERANCE,
        }
    )
    return components, {
        "amount_baseline": amount_baseline,
        "amount_comparison": amount_comparison,
        "total_delta": total_delta,
        "total_abs_delta": _numeric_column_sum(
            panel_frame.with_columns(pl.col("total_delta").abs().alias("_abs_delta")),
            "_abs_delta",
        ),
        "component_sum": component_sum,
        "other_residual": residual,
    }


def _dominant_component(components: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the largest component by absolute amount."""

    if not components:
        return {"variance_type": "", "variance_amount": 0.0}
    return max(components, key=lambda item: abs(float(item["variance_amount"] or 0.0)))


def _small_multiples_summary_markdown(context: dict[str, Any]) -> str:
    """Return a markdown chart-data block for Codex's business interpretation."""

    if context.get("status") != "written":
        return ""
    lines = [
        "",
        "## Standard Variance Small Multiples",
        "",
        f"- Dimension: `{context.get('dimension')}`",
        f"- Panel count: `{context.get('panel_count')}`",
        f"- Other member panel: `{context.get('has_other_member_panel')}`",
        f"- Any residual Balance component: `{context.get('has_residual_balance_component')}`",
        "- Source files: `waterfall_small_multiples.png`, "
        "`waterfall_small_multiples_summary.csv`, "
        "`waterfall_small_multiples_context.json`",
        "",
        "Top panels by absolute variance:",
    ]
    for panel in context.get("panels", [])[:6]:
        dominant = panel.get("dominant_component") or {}
        lines.append(
            "- "
            f"{panel.get('dimension_value')}: total_delta="
            f"{float(panel.get('total_delta') or 0.0):,.2f}; "
            f"dominant={dominant.get('variance_type')} "
            f"{float(dominant.get('variance_amount') or 0.0):,.2f}"
        )
    lines.extend(
        [
            "",
            "Codex must use this source data when explaining whether the standard "
            "variance story is concentrated in specific dimension members or "
            "spread across the selected dimension.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_waterfall_small_multiples_chart_data(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
) -> tuple[list[str], dict[str, Any], str]:
    """Write data context for the standard-variance small-multiples chart."""

    options = recipe.get("options") or {}
    if not bool(options.get("waterfall_chart", True)):
        return [], {"enabled": False, "status": "disabled_waterfall_chart"}, ""
    if not bool(options.get("waterfall_small_multiples", False)):
        return [], {"enabled": False, "status": "disabled_no_selected_dimension"}, ""
    dimension = options.get("waterfall_small_multiples_dimension")
    if not dimension or str(dimension) not in result.schema:
        return (
            [],
            {
                "enabled": True,
                "status": "not_written_no_dimension",
                "dimension": str(dimension or ""),
            },
            "",
        )

    dimension = str(dimension)
    working, panel_specs, has_other_member_panel = _small_multiples_panel_slices(
        result,
        dimension,
    )
    if not panel_specs:
        return (
            [],
            {
                "enabled": True,
                "status": "not_written_no_panel_values",
                "dimension": dimension,
            },
            "",
        )

    rows: list[dict[str, Any]] = []
    panels: list[dict[str, Any]] = []
    total_abs_delta = _numeric_column_sum(
        working.with_columns(pl.col("total_delta").abs().alias("_abs_delta")),
        "_abs_delta",
    )
    has_residual_balance_component = False
    for panel in panel_specs:
        panel_frame = _small_multiples_panel_frame(working, panel)
        components, totals = _panel_component_values(panel_frame, recipe)
        dominant = _dominant_component(components)
        has_residual_balance_component = (
            has_residual_balance_component or abs(totals["other_residual"]) > TOLERANCE
        )
        included_member_count = len(panel["selected_values"])
        panel_payload = {
            "panel_number": panel["panel_number"],
            "dimension": dimension,
            "dimension_value": panel["dimension_value"],
            "panel_type": panel["panel_type"],
            "included_member_count": included_member_count,
            "source_result_rows": panel_frame.height,
            "amount_baseline": totals["amount_baseline"],
            "amount_comparison": totals["amount_comparison"],
            "total_delta": totals["total_delta"],
            "total_abs_delta": totals["total_abs_delta"],
            "share_of_all_panel_abs_delta": (
                totals["total_abs_delta"] / total_abs_delta if total_abs_delta else 0.0
            ),
            "other_residual": totals["other_residual"],
            "dominant_component": {
                "variance_type": dominant.get("variance_type"),
                "variance_amount": dominant.get("variance_amount"),
            },
            "components": components,
        }
        panels.append(panel_payload)
        abs_component_total = sum(
            abs(float(component["variance_amount"] or 0.0)) for component in components
        )
        for component in components:
            amount = float(component["variance_amount"] or 0.0)
            rows.append(
                {
                    "panel_number": panel["panel_number"],
                    "dimension": dimension,
                    "dimension_value": panel["dimension_value"],
                    "panel_type": panel["panel_type"],
                    "included_member_count": included_member_count,
                    "source_result_rows": panel_frame.height,
                    "amount_baseline": totals["amount_baseline"],
                    "amount_comparison": totals["amount_comparison"],
                    "total_delta": totals["total_delta"],
                    "total_abs_delta": totals["total_abs_delta"],
                    "share_of_all_panel_abs_delta": (
                        totals["total_abs_delta"] / total_abs_delta
                        if total_abs_delta
                        else 0.0
                    ),
                    "variance_type": component["variance_type"],
                    "variance_amount": amount,
                    "share_of_panel_abs_components": (
                        abs(amount) / abs_component_total
                        if abs_component_total
                        else 0.0
                    ),
                    "is_residual_other": component["is_residual_other"],
                    "is_residual_balance": component.get(
                        "is_residual_balance",
                        False,
                    ),
                    "displayed_in_chart": component["displayed_in_chart"],
                }
            )

    panels.sort(key=lambda item: abs(float(item["total_delta"] or 0.0)), reverse=True)
    summary_path = output_dir / "waterfall_small_multiples_summary.csv"
    context_path = output_dir / "waterfall_small_multiples_context.json"
    pl.DataFrame(rows).write_csv(summary_path)
    context = {
        "analysis_type": "standard_variance_small_multiples",
        "status": "written",
        "dimension": dimension,
        "panel_limit": SMALL_MULTIPLES_PANEL_LIMIT,
        "panel_count": len(panel_specs),
        "has_other_member_panel": has_other_member_panel,
        "has_residual_other_component": has_residual_balance_component,
        "has_residual_balance_component": has_residual_balance_component,
        "chart_component_mode": "legacy_price_units_mix_balance",
        "chart_artifact": "waterfall_small_multiples.png",
        "summary_csv": summary_path.name,
        "context_json": context_path.name,
        "selection": options.get("waterfall_small_multiples_dimension_selection"),
        **_title_contract_payload(
            recipe,
            chart_kind="standard_small_multiples",
            dimension=str(dimension),
        ),
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "required_points": [
                "Use panel labels and values to explain concentration or spread by dimension member.",
                "Explain the dominant variance type within the largest panels.",
                "Call out the Others aggregated member panel when it exists.",
                "Call out residual Balance components when they are material.",
                "Do not treat panel members as additional bridge rows; each panel repeats the same standard variance bridge.",
            ],
        },
        "panels": panels,
    }
    write_json(context_path, context)
    audit = {
        "enabled": True,
        "status": "written",
        "dimension": dimension,
        "summary_csv": summary_path.name,
        "context_json": context_path.name,
        "panel_count": len(panel_specs),
        "has_other_member_panel": has_other_member_panel,
        "has_residual_other_component": has_residual_balance_component,
        "has_residual_balance_component": has_residual_balance_component,
        "chart_component_mode": "legacy_price_units_mix_balance",
    }
    return (
        [str(summary_path), str(context_path)],
        audit,
        _small_multiples_summary_markdown(context),
    )


def suggested_calculation_grain(
    candidates: list[str], dimensions: list[str]
) -> list[str]:
    """Return lower-level PVM grain when product or customer columns exist."""

    selected: list[str] = []
    normalized = [(column, normalize_name(column)) for column in candidates]
    for hint in CALCULATION_GRAIN_NAME_PRIORITY:
        normalized_hint = normalize_name(hint)
        for column, normalized_name in normalized:
            if normalized_name == normalized_hint and column not in selected:
                selected.append(column)
    return selected or dimensions


def infer_mappings(df: pl.DataFrame) -> dict[str, Any]:
    """Infer a suggested recipe mapping from column names and dtypes."""

    columns, _schema = get_schema_and_column_names(df)
    mapping: dict[str, Any] = {}
    for key, hints in COLUMN_HINTS.items():
        mapping[key] = first_matching_column(columns, hints)
    mapping["date_column"] = suggested_date_column(df, columns)
    mapping["period_column"] = (
        plan_actual_scenario_column(df, columns) or mapping["period_column"]
    )

    schema = df.schema
    period_col = mapping["period_column"]
    metric_cols = {
        value
        for value in (
            mapping["amount_column"],
            mapping["units_column"],
            mapping["discount_column"],
            mapping["cogs_column"],
            mapping["date_column"],
            period_col,
        )
        if value
    }
    dimension_candidates = [
        column
        for column in columns
        if column not in metric_cols
        and not is_numeric_dtype(schema[column])
        and not is_temporal_dtype(schema[column])
    ]
    if not dimension_candidates:
        dimension_candidates = [
            column
            for column in columns
            if column not in metric_cols and column != period_col
        ][:2]
    dimensions = ranked_dimension_candidates(dimension_candidates)[:4]
    mapping["dimensions"] = dimensions
    mapping["calculation_grain"] = suggested_calculation_grain(
        dimension_candidates, dimensions
    )
    return mapping


def period_values(df: pl.DataFrame, period_col: str | None) -> list[str]:
    """Return sorted non-null period values as strings."""

    if not period_col or period_col not in df.schema:
        return []
    values = (
        df.select(pl.col(period_col).cast(pl.Utf8).drop_nulls().unique().sort())
        .to_series(0)
        .to_list()
    )
    return [str(value) for value in values]


def suggested_period_pair(
    df: pl.DataFrame, period_col: str | None, periods: list[str]
) -> tuple[str | None, str | None]:
    """Return suggested baseline and comparison period values."""

    if is_scenario_comparison_column(df, period_col):
        return default_scenario_comparison_pair(periods)
    return (
        periods[0] if len(periods) >= 1 else None,
        periods[1] if len(periods) >= 2 else None,
    )


def suggested_comparison_options(
    df: pl.DataFrame, period_col: str | None
) -> dict[str, str]:
    """Return advisory comparison metadata for Codex intake and review."""

    if is_scenario_comparison_column(df, period_col):
        return {
            "comparison_basis": COMPARISON_BASIS_SCENARIO,
            "period_comparison_mode": PERIOD_MODE_NOT_APPLICABLE,
        }
    return {
        "comparison_basis": COMPARISON_BASIS_PERIOD,
        "period_comparison_mode": PERIOD_MODE_CALENDAR,
    }


def legacy_period_mode_from_period_type(period_type: str) -> str:
    """Return the legacy variance period mode for a normalized period type."""

    if period_type == PERIOD_TYPE_ROLLING:
        return PERIOD_MODE_ROLLING
    if period_type in {PERIOD_TYPE_TO_DATE, PERIOD_TYPE_FISCAL}:
        return PERIOD_MODE_YEAR_TO_DATE
    if period_type == PERIOD_TYPE_CUSTOM:
        return PERIOD_MODE_CUSTOM
    return PERIOD_MODE_CALENDAR


def build_recipe(
    source_path: Path,
    df: pl.DataFrame,
    *,
    language: str,
    existing_recipe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a suggested or merged variance recipe."""

    mapping = infer_mappings(df)
    periods = period_values(df, mapping["period_column"])
    baseline_period, comparison_period = suggested_period_pair(
        df, mapping["period_column"], periods
    )
    suggested_small_multiples_dimension = (
        mapping["dimensions"][0] if len(mapping["dimensions"]) == 1 else None
    )
    suggested_comparison = suggested_comparison_options(df, mapping["period_column"])
    suggested_period_contract = period_contract_options(
        suggested_comparison,
        default_type=(
            PERIOD_TYPE_CUSTOM
            if suggested_comparison["comparison_basis"] == COMPARISON_BASIS_SCENARIO
            else "calendar"
        ),
    )
    suggested = {
        "schema_version": SCHEMA_VERSION,
        "language": language,
        "source_file": str(source_path),
        "mappings": {
            "period_column": mapping["period_column"],
            "baseline_period": baseline_period,
            "comparison_period": comparison_period,
            "amount_column": mapping["amount_column"],
            "units_column": mapping["units_column"],
            "discount_column": mapping["discount_column"],
            "cogs_column": mapping["cogs_column"],
            "date_column": mapping["date_column"],
            "dimensions": mapping["dimensions"],
            "calculation_grain": mapping["calculation_grain"],
        },
        "options": {
            **suggested_comparison,
            **suggested_period_contract,
            "currency": "EUR",
            "unit_label": "units",
            "root_cause_bridge": True,
            "root_cause_bridge_alternative_result": 1,
            "root_cause_bridge_drilldown_rows": [],
            "root_cause_bridge_drilldown_all": False,
            "root_cause_bridge_move_rows": {},
            "root_cause_bridge_alternative_sweep": True,
            "root_cause_bridge_alternative_sweep_start": 1,
            "root_cause_bridge_alternative_sweep_end": 10,
            "root_cause_bridge_auto_drilldown": "all_selected",
            "root_cause_bridge_auto_drilldown_min_share": 0.75,
            "root_cause_component_bridge": False,
            "root_cause_component_bridge_alternative_result": 1,
            "waterfall_chart": True,
            "pvm_decomposition_ladder": True,
            "waterfall_small_multiples": bool(mapping["dimensions"]),
            "waterfall_small_multiples_dimension": suggested_small_multiples_dimension,
            "total_by_dimension_bridge": bool(mapping["dimensions"]),
            "total_by_dimension_bridge_dimension": None,
            "total_by_dimension_bridge_top_n": TOTAL_BY_DIMENSION_DEFAULT_TOP_N,
            "exploded_variance_bridge": len(mapping["dimensions"]) >= 2,
            "exploded_variance_bridge_parent_dimension": None,
            "exploded_variance_bridge_child_dimension": None,
            "exploded_variance_bridge_parent_top_n": TOTAL_BY_DIMENSION_DEFAULT_TOP_N,
            "exploded_variance_bridge_child_top_n": EXPLODED_BRIDGE_DEFAULT_CHILD_TOP_N,
            "exploded_variance_bridge_max_drilldowns": (
                EXPLODED_BRIDGE_DEFAULT_MAX_DRILLDOWNS
            ),
        },
    }
    if not existing_recipe:
        return suggested

    merged = dict(suggested)
    merged.update(
        {k: v for k, v in existing_recipe.items() if k not in {"mappings", "options"}}
    )
    merged["mappings"] = {
        **suggested["mappings"],
        **existing_recipe.get("mappings", {}),
    }
    merged["options"] = {**suggested["options"], **existing_recipe.get("options", {})}
    return merged


def inspect_variance_inputs(
    input_path: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
) -> InspectionResult:
    """Inspect a variance input file and write inspection and recipe JSON."""

    df = read_table(input_path)
    columns, schema = get_schema_and_column_names(df)
    existing_recipe = load_json(recipe_path) if recipe_path else None
    recipe = build_recipe(
        input_path, df, language=language, existing_recipe=existing_recipe
    )
    mappings = recipe["mappings"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "language": language,
        "source_file": str(input_path),
        "row_count": df.height,
        "columns": [{"name": column, "dtype": schema[column]} for column in columns],
        "available_analysis_context": available_analysis_context(df),
        "period_values": period_values(df, mappings.get("period_column")),
        "suggested_mappings": mappings,
        "sample_rows": df.head(10).to_dicts(),
        "warnings": inspection_warnings(df, mappings),
    }
    warn_if_output_dir_has_existing_files(output_dir, "Inspection")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "inspection.json", payload)
    write_json(output_dir / "suggested_recipe.json", recipe)
    return InspectionResult(payload=payload, recipe=recipe)


def inspection_warnings(df: pl.DataFrame, mappings: dict[str, Any]) -> list[str]:
    """Return deterministic warnings about missing or incomplete mappings."""

    warnings: list[str] = []
    required = {
        "period_column": "Period column is required.",
        "baseline_period": "Baseline period is required.",
        "comparison_period": "Comparison period is required.",
        "amount_column": "Amount/sales column is required.",
    }
    for key, message in required.items():
        if not mappings.get(key):
            warnings.append(message)
    columns, _schema = get_schema_and_column_names(df)
    for key in (
        "period_column",
        "amount_column",
        "units_column",
        "discount_column",
        "cogs_column",
        "date_column",
    ):
        value = mappings.get(key)
        if value and value not in columns:
            warnings.append(f"Mapped {key} does not exist in input columns: {value}")
    for dimension in mappings.get("dimensions") or []:
        if dimension not in columns:
            warnings.append(
                f"Mapped dimension does not exist in input columns: {dimension}"
            )
    return warnings


def parsed_date_expression(column: str) -> pl.Expr:
    """Return a date expression for common sales-export date representations."""

    text = pl.col(column).cast(pl.Utf8)
    return pl.coalesce(
        [
            pl.col(column).cast(pl.Date, strict=False),
            text.str.strptime(pl.Date, "%Y-%m-%d", strict=False),
            text.str.strptime(pl.Date, "%Y/%m/%d", strict=False),
            text.str.strptime(pl.Date, "%d/%m/%Y", strict=False),
            text.str.strptime(pl.Date, "%m/%d/%Y", strict=False),
            text.str.strptime(pl.Date, "%Y-%m", strict=False),
            text.str.strptime(pl.Date, "%b-%Y", strict=False),
        ]
    )


def as_date(value: Any) -> date:
    """Return a Python date from legacy or Polars date values."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError(f"Expected a date value, got {value!r}")


def add_months(value: date, months: int) -> date:
    """Shift a date by whole months, preserving the closest valid day."""

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def fiscal_year_start_for(value: date, fiscal_start_month: int) -> date:
    """Return the fiscal/calendar year start for a cutoff date."""

    year = value.year if value.month >= fiscal_start_month else value.year - 1
    return date(year, fiscal_start_month, 1)


def int_option(options: dict[str, Any], key: str, default: int) -> int:
    """Return a positive integer option with a conservative fallback."""

    try:
        value = int(options.get(key, default))
    except (TypeError, ValueError):
        value = default
    return value if value > 0 else default


def rolling_window_length_options(
    options: dict[str, Any], period_grain: str
) -> dict[str, int]:
    """Return a rolling window length from explicit options or period grain.

    This rule is deterministic because the grain-to-window mapping is mechanical:
    week=7 days, month=1 month, quarter=3 months, year=12 months.
    """

    if options.get("rolling_window_days") is not None:
        return {"days": int_option(options, "rolling_window_days", 7)}
    if options.get("rolling_window_months") is not None:
        return {"months": int_option(options, "rolling_window_months", 12)}
    if period_grain == PERIOD_GRAIN_WEEK:
        return {"days": 7}
    if period_grain == PERIOD_GRAIN_MONTH:
        return {"months": 1}
    if period_grain == PERIOD_GRAIN_QUARTER:
        return {"months": 3}
    if period_grain == PERIOD_GRAIN_YEAR:
        return {"months": 12}
    return {"months": 12}


def bounded_int_option(
    options: dict[str, Any], key: str, default: int, *, minimum: int, maximum: int
) -> int:
    """Return an integer option clamped to an inclusive range."""

    value = int_option(options, key, default)
    return min(max(value, minimum), maximum)


def bounded_float_option(
    options: dict[str, Any], key: str, default: float, *, minimum: float, maximum: float
) -> float:
    """Return a float option clamped to an inclusive range."""

    try:
        value = float(options.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def positive_int_list_option(options: dict[str, Any], key: str) -> list[int]:
    """Return unique positive integers from an option list."""

    raw_value = options.get(key, [])
    if raw_value is None:
        return []
    values = raw_value if isinstance(raw_value, list) else [raw_value]
    result: list[int] = []
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in result:
            result.append(parsed)
    return result


def move_rows_option(options: dict[str, Any], key: str) -> dict[str, list[int]]:
    """Return normalized legacy move-row mappings with string keys."""

    raw_value = options.get(key, {})
    if not isinstance(raw_value, dict):
        return {}
    result: dict[str, list[int]] = {}
    for main_row, drilldown_rows in raw_value.items():
        try:
            parsed_main = int(main_row)
        except (TypeError, ValueError):
            continue
        if parsed_main <= 0:
            continue
        values = (
            drilldown_rows if isinstance(drilldown_rows, list) else [drilldown_rows]
        )
        parsed_rows: list[int] = []
        for row in values:
            try:
                parsed_row = int(row)
            except (TypeError, ValueError):
                continue
            if parsed_row > 0 and parsed_row not in parsed_rows:
                parsed_rows.append(parsed_row)
        if parsed_rows:
            result[str(parsed_main)] = parsed_rows
    return result


def root_cause_auto_drilldown_option(options: dict[str, Any]) -> str:
    """Return a supported automatic root-cause drilldown mode."""

    mode = (
        str(options.get("root_cause_bridge_auto_drilldown") or "none")
        .strip()
        .lower()
        .replace("-", "_")
    )
    return mode if mode in ROOT_CAUSE_AUTO_DRILLDOWN_VALUES else "none"


def between_dates(column: str, start: date, end: date) -> pl.Expr:
    """Return an inclusive date-window predicate."""

    return (pl.col(column) >= pl.lit(start)) & (pl.col(column) <= pl.lit(end))


def period_window_metadata(
    *,
    mode: str,
    date_column: str,
    baseline_label: str,
    baseline_start: date,
    baseline_end: date,
    comparison_label: str,
    comparison_start: date,
    comparison_end: date,
    legacy_context: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an auditable period-window payload for the used recipe."""

    payload = {
        "mode": mode,
        "date_column": date_column,
        "source": "legacy_date_period_context",
        "most_recent_date": as_date(legacy_context["most_recent_date"]),
        "least_recent_date": as_date(legacy_context["least_recent_date"]),
        "period_length_months": legacy_context["period_length_months"],
        "baseline": {
            "label": baseline_label,
            "start_date": baseline_start,
            "end_date": baseline_end,
        },
        "comparison": {
            "label": comparison_label,
            "start_date": comparison_start,
            "end_date": comparison_end,
        },
    }
    if extra:
        payload.update(extra)
    return payload


def prepare_period_comparison_buckets(
    df: pl.DataFrame,
    recipe: dict[str, Any],
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Create legacy-backed YTD/rolling buckets before variance arithmetic.

    This deterministic step is justified because date-window boundaries are
    mechanically verifiable and must be reproducible for audit review.
    """

    options = dict(recipe.get("options") or {})
    normalized_period_contract = period_contract_options(options)
    if options.get("period_type") and options.get("period_comparison_mode") in {
        None,
        PERIOD_MODE_CALENDAR,
    }:
        mode = legacy_period_mode_from_period_type(
            str(normalized_period_contract["period_type"])
        )
    elif options.get("period_comparison_mode"):
        mode = str(options.get("period_comparison_mode"))
        if mode not in PERIOD_COMPARISON_MODE_VALUES:
            mode = legacy_period_mode_from_period_type(
                str(normalized_period_contract["period_type"])
            )
    else:
        mode = legacy_period_mode_from_period_type(
            str(normalized_period_contract["period_type"])
        )
    if mode not in {PERIOD_MODE_YEAR_TO_DATE, PERIOD_MODE_ROLLING}:
        return df, recipe

    mappings = dict(recipe["mappings"])
    date_column = mappings.get("date_column") or mappings.get("period_column")
    if not date_column or date_column not in df.schema:
        raise ValueError(
            "A date_column mapping is required for year-to-date or rolling periods."
        )

    prepared = df.with_columns(
        parsed_date_expression(date_column).alias(DATE_WORK_COLUMN)
    )
    valid_date_rows = prepared.filter(pl.col(DATE_WORK_COLUMN).is_not_null())
    if valid_date_rows.is_empty():
        raise ValueError(
            f"Could not parse any dates from mapped date column: {date_column}"
        )

    legacy_context = legacy_date_period_context(valid_date_rows, DATE_WORK_COLUMN)
    comparison_end = as_date(legacy_context["most_recent_date"])
    period_specific_options: dict[str, Any] = {}

    if mode == PERIOD_MODE_YEAR_TO_DATE:
        fiscal_start_month = int_option(options, "fiscal_start_month", 1)
        if fiscal_start_month > 12:
            fiscal_start_month = 1
        comparison_start = fiscal_year_start_for(comparison_end, fiscal_start_month)
        baseline_start = add_months(comparison_start, -12)
        baseline_end = add_months(comparison_end, -12)
        baseline_label = str(legacy_context["ytd_baseline_label"])
        comparison_label = str(legacy_context["ytd_label"])
        period_window = period_window_metadata(
            mode=mode,
            date_column=date_column,
            baseline_label=baseline_label,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            comparison_label=comparison_label,
            comparison_start=comparison_start,
            comparison_end=comparison_end,
            legacy_context=legacy_context,
            extra={"fiscal_start_month": fiscal_start_month},
        )
    else:
        window_length = rolling_window_length_options(
            options, str(normalized_period_contract["period_grain"])
        )
        rolling_comparison = str(
            options.get("rolling_comparison") or ROLLING_COMPARISON_PRIOR_YEAR
        )
        if rolling_comparison not in ROLLING_COMPARISON_VALUES:
            rolling_comparison = ROLLING_COMPARISON_PRIOR_YEAR
        if "days" in window_length:
            window_days = window_length["days"]
            comparison_start = comparison_end - timedelta(days=window_days - 1)
            if rolling_comparison == ROLLING_COMPARISON_PREVIOUS_WINDOW:
                baseline_end = comparison_start - timedelta(days=1)
                baseline_start = baseline_end - timedelta(days=window_days - 1)
                baseline_label = (
                    f"previous_{window_days}d_"
                    f"{baseline_start.isoformat()}_{baseline_end.isoformat()}"
                )
            else:
                baseline_end = add_months(comparison_end, -12)
                baseline_start = baseline_end - timedelta(days=window_days - 1)
                baseline_label = (
                    f"prior_year_{window_days}d_"
                    f"{baseline_start.isoformat()}_{baseline_end.isoformat()}"
                )
            comparison_label = (
                f"rolling_{window_days}d_"
                f"{comparison_start.isoformat()}_{comparison_end.isoformat()}"
            )
            rolling_extra = {
                "rolling_window_days": window_days,
                "rolling_comparison": rolling_comparison,
            }
        else:
            window_months = window_length["months"]
            comparison_start = add_months(comparison_end, -(window_months - 1)).replace(
                day=1
            )
            if rolling_comparison == ROLLING_COMPARISON_PREVIOUS_WINDOW:
                baseline_start = add_months(comparison_start, -window_months)
                baseline_end = comparison_start - timedelta(days=1)
                baseline_label = (
                    f"previous_{window_months}m_"
                    f"{baseline_start.isoformat()}_{baseline_end.isoformat()}"
                )
            else:
                baseline_start = add_months(comparison_start, -12)
                baseline_end = add_months(comparison_end, -12)
                baseline_label = str(legacy_context["rolling_baseline_label"])
            comparison_label = str(legacy_context["rolling_label"])
            rolling_extra = {
                "rolling_window_months": window_months,
                "rolling_comparison": rolling_comparison,
            }
        period_specific_options = rolling_extra
        period_window = period_window_metadata(
            mode=mode,
            date_column=date_column,
            baseline_label=baseline_label,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            comparison_label=comparison_label,
            comparison_start=comparison_start,
            comparison_end=comparison_end,
            legacy_context=legacy_context,
            extra=rolling_extra,
        )

    prepared = prepared.with_columns(
        pl.when(between_dates(DATE_WORK_COLUMN, baseline_start, baseline_end))
        .then(pl.lit(baseline_label))
        .when(between_dates(DATE_WORK_COLUMN, comparison_start, comparison_end))
        .then(pl.lit(comparison_label))
        .otherwise(None)
        .alias(SYNTHETIC_PERIOD_COLUMN)
    ).drop(DATE_WORK_COLUMN)

    bucket_counts = {
        row[SYNTHETIC_PERIOD_COLUMN]: row["len"]
        for row in prepared.group_by(SYNTHETIC_PERIOD_COLUMN)
        .len()
        .filter(pl.col(SYNTHETIC_PERIOD_COLUMN).is_not_null())
        .to_dicts()
    }
    if not bucket_counts.get(baseline_label) or not bucket_counts.get(comparison_label):
        raise ValueError(
            "Prepared period windows do not contain both baseline and comparison rows."
        )

    mappings.update(
        {
            "period_column": SYNTHETIC_PERIOD_COLUMN,
            "baseline_period": baseline_label,
            "comparison_period": comparison_label,
        }
    )
    options.update(
        {
            "comparison_basis": COMPARISON_BASIS_PERIOD,
            "period_comparison_mode": mode,
            "period_type": normalized_period_contract["period_type"],
            "period_grain": normalized_period_contract["period_grain"],
            "fiscal_start_month": (
                fiscal_start_month
                if mode == PERIOD_MODE_YEAR_TO_DATE
                else normalized_period_contract["fiscal_start_month"]
            ),
            "period_window": {
                **period_window,
                "row_counts": bucket_counts,
            },
            **period_specific_options,
        }
    )
    updated_recipe = {**recipe, "mappings": mappings, "options": options}
    return prepared, updated_recipe


def validate_recipe(df: pl.DataFrame, recipe: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the recipe used for deterministic calculations."""

    mappings = dict(recipe.get("mappings") or {})
    options = dict(recipe.get("options") or {})
    columns, schema = get_schema_and_column_names(df)
    required_keys = (
        "period_column",
        "baseline_period",
        "comparison_period",
        "amount_column",
    )
    missing = [key for key in required_keys if not mappings.get(key)]
    if missing:
        raise ValueError(f"Missing required recipe mappings: {', '.join(missing)}")
    for key in (
        "period_column",
        "amount_column",
        "units_column",
        "discount_column",
        "cogs_column",
        "date_column",
    ):
        column = mappings.get(key)
        if column and column not in columns:
            raise ValueError(
                f"Recipe mapping '{key}' references missing column '{column}'"
            )
    for key in ("amount_column", "units_column", "discount_column", "cogs_column"):
        column = mappings.get(key)
        if column and not is_numeric_dtype(df.schema[column]):
            raise ValueError(
                f"Recipe mapping '{key}' must be numeric: {column} ({schema[column]})"
            )
    dimensions = mappings.get("dimensions") or []
    if not isinstance(dimensions, list):
        raise ValueError("Recipe mapping 'dimensions' must be a list of column names.")
    cohort_source_dimensions = recipe_cohort_source_dimensions(recipe)
    missing_cohort_sources = [
        column for column in cohort_source_dimensions if column not in columns
    ]
    if missing_cohort_sources:
        raise ValueError(
            "Recipe cohort source columns are missing: "
            + ", ".join(missing_cohort_sources)
        )
    cohort_dimension_names = recipe_cohort_dimension_names(recipe)
    missing_dimensions = [
        column
        for column in dimensions
        if column not in columns and column not in cohort_dimension_names
    ]
    if missing_dimensions:
        raise ValueError(
            "Recipe dimensions reference missing columns: "
            + ", ".join(missing_dimensions)
        )
    calculation_grain = mappings.get("calculation_grain")
    if calculation_grain is None:
        calculation_grain = dimensions
    if not isinstance(calculation_grain, list):
        raise ValueError(
            "Recipe mapping 'calculation_grain' must be a list of column names."
        )
    missing_grain = [
        column
        for column in calculation_grain
        if column not in columns and column not in cohort_dimension_names
    ]
    if missing_grain:
        raise ValueError(
            "Recipe calculation_grain references missing columns: "
            + ", ".join(missing_grain)
        )
    mappings["dimensions"] = dimensions
    mappings["calculation_grain"] = calculation_grain
    default_comparison_options = suggested_comparison_options(
        df, mappings.get("period_column")
    )
    comparison_basis = str(
        options.get("comparison_basis")
        or default_comparison_options["comparison_basis"]
    )
    if comparison_basis not in COMPARISON_BASIS_VALUES:
        comparison_basis = default_comparison_options["comparison_basis"]
    default_period_mode = default_comparison_options["period_comparison_mode"]
    normalized_period_contract = period_contract_options(
        options,
        default_type=(
            PERIOD_TYPE_CUSTOM
            if comparison_basis == COMPARISON_BASIS_SCENARIO
            else "calendar"
        ),
    )
    requested_period_mode = options.get("period_comparison_mode")
    if options.get("period_type") and requested_period_mode in {
        None,
        PERIOD_MODE_CALENDAR,
    }:
        period_comparison_mode = legacy_period_mode_from_period_type(
            str(normalized_period_contract["period_type"])
        )
    elif requested_period_mode:
        period_comparison_mode = str(requested_period_mode)
    elif options.get("period_type") or options.get("fiscal_start_month"):
        period_comparison_mode = legacy_period_mode_from_period_type(
            str(normalized_period_contract["period_type"])
        )
    else:
        period_comparison_mode = default_period_mode
    if period_comparison_mode not in PERIOD_COMPARISON_MODE_VALUES:
        period_comparison_mode = legacy_period_mode_from_period_type(
            str(normalized_period_contract["period_type"])
        )
    if (
        comparison_basis == COMPARISON_BASIS_PERIOD
        and period_comparison_mode == PERIOD_MODE_NOT_APPLICABLE
    ):
        period_comparison_mode = PERIOD_MODE_CALENDAR
    root_cause_enabled = bool(options.get("root_cause_bridge", True))
    root_cause_auto_drilldown = root_cause_auto_drilldown_option(options)
    if root_cause_enabled and root_cause_auto_drilldown == "none":
        root_cause_auto_drilldown = "all_selected"
    default_waterfall_small_multiples = bool(dimensions)
    waterfall_small_multiples = bool(
        options.get("waterfall_small_multiples", default_waterfall_small_multiples)
    )
    waterfall_small_multiples_dimension = options.get(
        "waterfall_small_multiples_dimension"
    )
    total_by_dimension_bridge = bool(
        options.get("total_by_dimension_bridge", bool(dimensions))
    )
    total_by_dimension_bridge_dimension = options.get(
        "total_by_dimension_bridge_dimension"
    )
    exploded_variance_bridge = bool(
        options.get("exploded_variance_bridge", len(dimensions) >= 2)
    )
    exploded_variance_bridge_parent_dimension = options.get(
        "exploded_variance_bridge_parent_dimension"
    )
    exploded_variance_bridge_child_dimension = options.get(
        "exploded_variance_bridge_child_dimension"
    )

    normalized = dict(recipe)
    normalized["schema_version"] = recipe.get("schema_version") or SCHEMA_VERSION
    normalized["mappings"] = mappings
    period_window = options.get("period_window")
    normalized["options"] = {
        "comparison_basis": comparison_basis,
        "period_comparison_mode": period_comparison_mode,
        "period_type": normalized_period_contract["period_type"],
        "period_grain": normalized_period_contract["period_grain"],
        "fiscal_start_month": normalized_period_contract["fiscal_start_month"],
        "period_window": period_window if isinstance(period_window, dict) else {},
        "currency": str(options.get("currency") or "EUR"),
        "unit_label": options.get("unit_label") or "units",
        "root_cause_bridge": root_cause_enabled,
        "root_cause_bridge_alternative_result": bounded_int_option(
            options,
            "root_cause_bridge_alternative_result",
            1,
            minimum=1,
            maximum=10,
        ),
        "root_cause_bridge_drilldown_rows": positive_int_list_option(
            options,
            "root_cause_bridge_drilldown_rows",
        ),
        "root_cause_bridge_drilldown_all": bool(
            options.get("root_cause_bridge_drilldown_all", False)
        ),
        "root_cause_bridge_move_rows": move_rows_option(
            options,
            "root_cause_bridge_move_rows",
        ),
        "root_cause_bridge_alternative_sweep": (
            root_cause_enabled
            and bool(options.get("root_cause_bridge_alternative_sweep", True))
        ),
        "root_cause_bridge_alternative_sweep_start": bounded_int_option(
            options,
            "root_cause_bridge_alternative_sweep_start",
            1,
            minimum=1,
            maximum=10,
        ),
        "root_cause_bridge_alternative_sweep_end": bounded_int_option(
            options,
            "root_cause_bridge_alternative_sweep_end",
            10,
            minimum=1,
            maximum=10,
        ),
        "root_cause_bridge_auto_drilldown": root_cause_auto_drilldown,
        "root_cause_bridge_auto_drilldown_min_share": bounded_float_option(
            options,
            "root_cause_bridge_auto_drilldown_min_share",
            0.75,
            minimum=0.0,
            maximum=1.0,
        ),
        "root_cause_component_bridge": root_cause_enabled
        and bool(options.get("root_cause_component_bridge", False)),
        "root_cause_component_bridge_alternative_result": bounded_int_option(
            options,
            "root_cause_component_bridge_alternative_result",
            1,
            minimum=1,
            maximum=10,
        ),
        "waterfall_chart": bool(options.get("waterfall_chart", True)),
        "pvm_decomposition_ladder": bool(options.get("pvm_decomposition_ladder", True)),
        "waterfall_small_multiples": waterfall_small_multiples,
        "waterfall_small_multiples_dimension": waterfall_small_multiples_dimension,
        "total_by_dimension_bridge": total_by_dimension_bridge,
        "total_by_dimension_bridge_dimension": total_by_dimension_bridge_dimension,
        "total_by_dimension_bridge_top_n": bounded_int_option(
            options,
            "total_by_dimension_bridge_top_n",
            TOTAL_BY_DIMENSION_DEFAULT_TOP_N,
            minimum=1,
            maximum=50,
        ),
        "exploded_variance_bridge": exploded_variance_bridge,
        "exploded_variance_bridge_parent_dimension": (
            exploded_variance_bridge_parent_dimension
        ),
        "exploded_variance_bridge_child_dimension": (
            exploded_variance_bridge_child_dimension
        ),
        "exploded_variance_bridge_parent_top_n": bounded_int_option(
            options,
            "exploded_variance_bridge_parent_top_n",
            TOTAL_BY_DIMENSION_DEFAULT_TOP_N,
            minimum=1,
            maximum=20,
        ),
        "exploded_variance_bridge_child_top_n": bounded_int_option(
            options,
            "exploded_variance_bridge_child_top_n",
            EXPLODED_BRIDGE_DEFAULT_CHILD_TOP_N,
            minimum=1,
            maximum=8,
        ),
        "exploded_variance_bridge_max_drilldowns": bounded_int_option(
            options,
            "exploded_variance_bridge_max_drilldowns",
            EXPLODED_BRIDGE_DEFAULT_MAX_DRILLDOWNS,
            minimum=1,
            maximum=EXPLODED_BRIDGE_DEFAULT_MAX_DRILLDOWNS,
        ),
    }
    if options.get("reporting_entity_label"):
        normalized["options"]["reporting_entity_label"] = str(
            options["reporting_entity_label"]
        )
    for key in (
        "cohorts",
        "cohort_definition",
        "cohort_contract",
        "derived_dimensions",
        "like_for_like",
        "cohort_current_period",
        "cohort_previous_period",
        "current_period_label",
        "previous_period_label",
        "recipe_cohort_audit",
    ):
        if key in options:
            normalized["options"][key] = options[key]
    sweep_start = normalized["options"]["root_cause_bridge_alternative_sweep_start"]
    sweep_end = normalized["options"]["root_cause_bridge_alternative_sweep_end"]
    if sweep_end < sweep_start:
        normalized["options"]["root_cause_bridge_alternative_sweep_start"] = sweep_end
        normalized["options"]["root_cause_bridge_alternative_sweep_end"] = sweep_start
    waterfall_dimension = normalized["options"]["waterfall_small_multiples_dimension"]
    if waterfall_dimension:
        waterfall_dimension = str(waterfall_dimension)
        if (
            waterfall_dimension not in columns
            and waterfall_dimension not in cohort_dimension_names
        ):
            raise ValueError(
                "Recipe option 'waterfall_small_multiples_dimension' references "
                f"missing column: {waterfall_dimension}"
            )
        normalized["options"][
            "waterfall_small_multiples_dimension"
        ] = waterfall_dimension
    total_bridge_dimension = normalized["options"][
        "total_by_dimension_bridge_dimension"
    ]
    if total_bridge_dimension:
        total_bridge_dimension = str(total_bridge_dimension)
        if (
            total_bridge_dimension not in columns
            and total_bridge_dimension not in cohort_dimension_names
        ):
            raise ValueError(
                "Recipe option 'total_by_dimension_bridge_dimension' references "
                f"missing column: {total_bridge_dimension}"
            )
        normalized["options"][
            "total_by_dimension_bridge_dimension"
        ] = total_bridge_dimension
    for option_key, role in (
        ("exploded_variance_bridge_parent_dimension", "parent"),
        ("exploded_variance_bridge_child_dimension", "child"),
    ):
        configured_dimension = normalized["options"][option_key]
        if not configured_dimension:
            continue
        configured_dimension = str(configured_dimension)
        if (
            configured_dimension not in columns
            and configured_dimension not in cohort_dimension_names
        ):
            raise ValueError(
                f"Recipe option '{option_key}' references missing {role} "
                f"column: {configured_dimension}"
            )
        normalized["options"][option_key] = configured_dimension
    if (
        normalized["options"].get("exploded_variance_bridge_parent_dimension")
        and normalized["options"].get("exploded_variance_bridge_child_dimension")
        and normalized["options"]["exploded_variance_bridge_parent_dimension"]
        == normalized["options"]["exploded_variance_bridge_child_dimension"]
    ):
        raise ValueError(
            "Recipe options 'exploded_variance_bridge_parent_dimension' and "
            "'exploded_variance_bridge_child_dimension' must differ."
        )
    if (
        period_comparison_mode == PERIOD_MODE_ROLLING
        or options.get("rolling_window_days") is not None
        or options.get("rolling_window_months") is not None
    ):
        rolling_window = rolling_window_length_options(
            options, str(normalized_period_contract["period_grain"])
        )
        if "days" in rolling_window:
            normalized["options"]["rolling_window_days"] = rolling_window["days"]
            normalized["options"].pop("rolling_window_months", None)
        else:
            normalized["options"]["rolling_window_months"] = rolling_window["months"]
            normalized["options"].pop("rolling_window_days", None)
    if options.get("rolling_comparison") is not None:
        normalized["options"]["rolling_comparison"] = str(
            options.get("rolling_comparison")
        )
    if options.get("fiscal_start_month") is not None:
        normalized["options"]["fiscal_start_month"] = normalized_period_contract[
            "fiscal_start_month"
        ]
    return normalized


def add_total_dimension(
    df: pl.DataFrame, dimensions: list[str]
) -> tuple[pl.DataFrame, list[str]]:
    """Add a deterministic total dimension when no dimensions are mapped."""

    if dimensions:
        return df, dimensions
    return df.with_columns(pl.lit("Total").alias(TOTAL_DIMENSION)), [TOTAL_DIMENSION]


def aggregate_period(
    df: pl.DataFrame,
    dimensions: list[str],
    period_col: str,
    period_value: str,
    value_columns: list[str],
    suffix: str,
) -> pl.DataFrame:
    """Aggregate one period snapshot and suffix value columns."""

    filtered = df.filter(pl.col(period_col).cast(pl.Utf8) == str(period_value))
    if filtered.is_empty():
        raise ValueError(f"No rows found for period '{period_value}'.")
    grouped = (
        filtered.lazy()
        .with_columns(
            [
                pl.col(column).fill_null("").cast(pl.Utf8).alias(column)
                for column in dimensions
            ]
        )
        .group_by(dimensions)
        .agg(
            [
                pl.col(column).sum().alias(f"{column}_{suffix}")
                for column in value_columns
            ]
        )
        .collect()
    )
    return grouped


def joined_period_frame(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    dimensions: list[str],
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Return a full outer joined baseline/comparison frame."""

    mappings = recipe["mappings"]
    period_col = mappings["period_column"]
    baseline_period = str(mappings["baseline_period"])
    comparison_period = str(mappings["comparison_period"])
    amount_col = mappings["amount_column"]
    optional_cols = [
        mappings.get("units_column"),
        mappings.get("discount_column"),
        mappings.get("cogs_column"),
    ]
    value_columns = [amount_col] + [column for column in optional_cols if column]
    value_columns = list(dict.fromkeys(value_columns))
    baseline = aggregate_period(
        df, dimensions, period_col, baseline_period, value_columns, "baseline"
    )
    comparison = aggregate_period(
        df, dimensions, period_col, comparison_period, value_columns, "comparison"
    )
    joined = baseline.join(comparison, on=dimensions, how="full", coalesce=True)
    fill_columns = [
        f"{column}_{suffix}"
        for column in value_columns
        for suffix in ("baseline", "comparison")
    ]
    joined = joined.with_columns(
        [pl.col(column).fill_null(0).alias(column) for column in fill_columns]
    )
    names = {
        "amount0": f"{amount_col}_baseline",
        "amount1": f"{amount_col}_comparison",
    }
    for key, source_key in (
        ("units", "units_column"),
        ("discount", "discount_column"),
        ("cogs", "cogs_column"),
    ):
        column = mappings.get(source_key)
        if column:
            names[f"{key}0"] = f"{column}_baseline"
            names[f"{key}1"] = f"{column}_comparison"
    return joined, names


def optional_col(names: dict[str, str], key: str) -> pl.Expr:
    """Return an optional numeric expression, defaulting to zero."""

    column = names.get(key)
    if column:
        return pl.col(column)
    return pl.lit(0.0)


def safe_ratio(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    """Return numerator / denominator, using zero when denominator is zero."""

    return pl.when(denominator == 0).then(0.0).otherwise(numerator / denominator)


def ordered_unique(values: Iterable[str]) -> list[str]:
    """Return values once, preserving their first-seen order."""

    return list(dict.fromkeys(values))


def calculation_grain_for(
    recipe: dict[str, Any], report_dimensions: list[str]
) -> list[str]:
    """Return the bottom-up grain used for legacy-compatible variance math."""

    mappings = recipe["mappings"]
    grain = list(mappings.get("calculation_grain") or report_dimensions)
    return ordered_unique([*report_dimensions, *grain])


def changed_mask(amount0: pl.Expr, amount1: pl.Expr) -> pl.Expr:
    """Return rows present in both periods for legacy price-volume-mix allocation."""

    return (amount0 > 0) & (amount1 > 0)


def new_or_lost_contribution(
    amount0: pl.Expr, amount1: pl.Expr, contribution: pl.Expr
) -> pl.Expr:
    """Put new/lost rows entirely into the volume-style contribution."""

    return (
        pl.when(amount0 == 0)
        .then(contribution)
        .when(amount1 == 0)
        .then(contribution)
        .otherwise(0.0)
    )


def legacy_price_component(
    amount0: pl.Expr, amount1: pl.Expr, units0: pl.Expr, units1: pl.Expr
) -> pl.Expr:
    """Legacy price effect from variance_formulas.calculate_residual_variance."""

    price0 = safe_ratio(amount0, units0)
    price1 = safe_ratio(amount1, units1)
    units_change = units1 - units0
    price_change = price1 - price0
    return (
        pl.when(changed_mask(amount0, amount1))
        .then(price_change * (units0 + units_change / 2))
        .otherwise(0.0)
    )


def legacy_volume_component(
    amount0: pl.Expr, amount1: pl.Expr, units0: pl.Expr, units1: pl.Expr
) -> pl.Expr:
    """Legacy volume effect with new/lost rows treated as volume variance."""

    price0 = safe_ratio(amount0, units0)
    price1 = safe_ratio(amount1, units1)
    units_change = units1 - units0
    price_change = price1 - price0
    total_delta = amount1 - amount0
    changed_volume = units_change * (price0 + price_change / 2)
    return (
        pl.when(changed_mask(amount0, amount1))
        .then(changed_volume)
        .otherwise(total_delta)
    )


def numeric_sum_expressions(
    df: pl.DataFrame, group_columns: list[str]
) -> list[pl.Expr]:
    """Return sum expressions for numeric non-grouping columns."""

    return [
        pl.col(column).sum().alias(column)
        for column, dtype in df.schema.items()
        if column not in group_columns and dtype.is_numeric()
    ]


def add_report_total_dimension(
    df: pl.DataFrame, report_dimensions: list[str]
) -> tuple[pl.DataFrame, list[str]]:
    """Add a total reporting dimension when the user asks for total output."""

    if report_dimensions:
        return df, report_dimensions
    return df.with_columns(pl.lit("Total").alias(TOTAL_DIMENSION)), [TOTAL_DIMENSION]


def calculate_variance_frame(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    dimensions: list[str],
) -> pl.DataFrame:
    """Calculate deterministic variance output using legacy bottom-up price-volume-mix."""

    reporting_dimensions = list(dimensions)
    leaf_dimensions = calculation_grain_for(recipe, reporting_dimensions)
    working_df, grouping_dimensions = add_total_dimension(df, leaf_dimensions)
    wide, names = joined_period_frame(working_df, recipe, grouping_dimensions)
    amount0 = pl.col(names["amount0"])
    amount1 = pl.col(names["amount1"])
    units0 = optional_col(names, "units0")
    units1 = optional_col(names, "units1")
    discount0 = optional_col(names, "discount0")
    discount1 = optional_col(names, "discount1")
    cogs0 = optional_col(names, "cogs0")
    cogs1 = optional_col(names, "cogs1")
    has_units = "units0" in names and "units1" in names
    has_discount = "discount0" in names and "discount1" in names
    has_cogs = "cogs0" in names and "cogs1" in names

    result = wide.with_columns(
        (amount1 - amount0).alias("total_delta"),
        pl.when(amount0 == 0)
        .then(None)
        .otherwise((amount1 - amount0) / amount0 * 100)
        .alias("amount_pct_change"),
        amount0.alias("_legacy_amount0"),
        amount1.alias("_legacy_amount1"),
    )
    if has_units:
        price0 = safe_ratio(amount0, units0)
        price1 = safe_ratio(amount1, units1)
        changed = changed_mask(amount0, amount1)
        result = result.with_columns(
            price0.alias("price_baseline"),
            price1.alias("price_comparison"),
            legacy_price_component(amount0, amount1, units0, units1).alias(
                "price_variance"
            ),
            legacy_volume_component(amount0, amount1, units0, units1).alias(
                "volume_variance"
            ),
            pl.when(changed)
            .then(amount0)
            .otherwise(0.0)
            .alias("_legacy_changed_amount0"),
            pl.when(changed)
            .then(amount1)
            .otherwise(0.0)
            .alias("_legacy_changed_amount1"),
            pl.when(changed)
            .then(units0)
            .otherwise(0.0)
            .alias("_legacy_changed_units0"),
            pl.when(changed)
            .then(units1)
            .otherwise(0.0)
            .alias("_legacy_changed_units1"),
            units0.alias("_legacy_units0"),
            units1.alias("_legacy_units1"),
            new_or_lost_contribution(amount0, amount1, amount1 - amount0).alias(
                "_legacy_new_lost_volume"
            ),
        )
        result = result.with_columns(
            pl.col("volume_variance").alias("_legacy_bottom_up_volume"),
            pl.lit(0.0).alias("mix_variance"),
        )
    if has_discount:
        net0 = amount0 - discount0
        net1 = amount1 - discount1
        result = result.with_columns(
            net0.alias("net_baseline"),
            net1.alias("net_comparison"),
            (net1 - net0).alias("net_delta"),
            pl.when(net0 == 0)
            .then(None)
            .otherwise((net1 - net0) / net0 * 100)
            .alias("net_pct_change"),
            (-(discount1 - discount0)).alias("discount_variance"),
            discount0.alias("_legacy_discount0"),
            discount1.alias("_legacy_discount1"),
        )
    if has_cogs:
        margin0 = amount0 - discount0 - cogs0
        margin1 = amount1 - discount1 - cogs1
        result = result.with_columns(
            (cogs1 - cogs0).alias("cogs_delta"),
            (-(cogs1 - cogs0)).alias("cogs_variance"),
            cogs0.alias("_legacy_cogs0"),
            cogs1.alias("_legacy_cogs1"),
            margin0.alias("margin_baseline"),
            margin1.alias("margin_comparison"),
            (margin1 - margin0).alias("margin_delta"),
            pl.when(margin0 == 0)
            .then(None)
            .otherwise((margin1 - margin0) / margin0 * 100)
            .alias("margin_pct_change"),
        )
        if has_units:
            changed = changed_mask(amount0, amount1)
            price0 = safe_ratio(amount0, units0)
            price1 = safe_ratio(amount1, units1)
            discount_per_unit0 = safe_ratio(discount0, units0)
            discount_per_unit1 = safe_ratio(discount1, units1)
            cogs_per_unit0 = safe_ratio(cogs0, units0)
            cogs_per_unit1 = safe_ratio(cogs1, units1)
            cost_per_unit0 = discount_per_unit0 + cogs_per_unit0
            cost_per_unit1 = discount_per_unit1 + cogs_per_unit1
            units_change = units1 - units0
            price_change = price1 - price0
            discount_change = discount_per_unit1 - discount_per_unit0
            cogs_change = cogs_per_unit1 - cogs_per_unit0
            cost_change = cost_per_unit1 - cost_per_unit0
            changed_weight = units0 + units_change / 2
            margin_volume = units_change * (
                price0 - cost_per_unit0 + price_change / 2 - cost_change / 2
            )
            result = result.with_columns(
                pl.when(changed)
                .then(price_change * (units0 + units_change / 2))
                .otherwise(0.0)
                .alias("margin_price_variance"),
                pl.when(changed)
                .then(-discount_change * changed_weight)
                .otherwise(0.0)
                .alias("discount_variance"),
                pl.when(changed)
                .then(-cogs_change * changed_weight)
                .otherwise(0.0)
                .alias("cogs_variance"),
                pl.when(changed)
                .then(margin_volume)
                .otherwise(margin1 - margin0)
                .alias("margin_volume_variance"),
                pl.when(changed)
                .then(discount0)
                .otherwise(0.0)
                .alias("_legacy_changed_discount0"),
                pl.when(changed)
                .then(discount1)
                .otherwise(0.0)
                .alias("_legacy_changed_discount1"),
                pl.when(changed)
                .then(cogs0)
                .otherwise(0.0)
                .alias("_legacy_changed_cogs0"),
                pl.when(changed)
                .then(cogs1)
                .otherwise(0.0)
                .alias("_legacy_changed_cogs1"),
                new_or_lost_contribution(amount0, amount1, margin1 - margin0).alias(
                    "_legacy_new_lost_margin_volume"
                ),
            )
            result = result.with_columns(
                pl.col("margin_volume_variance").alias(
                    "_legacy_bottom_up_margin_volume"
                ),
                pl.lit(0.0).alias("margin_mix_variance"),
            )
            result = result.with_columns(
                (
                    pl.col("margin_delta")
                    - pl.col("margin_price_variance")
                    - pl.col("margin_volume_variance")
                    - pl.col("margin_mix_variance")
                ).alias("margin_component_reconciliation_delta")
            )
    result = aggregate_legacy_components(
        result,
        reporting_dimensions,
        has_units=has_units,
        has_discount=has_discount,
        has_cogs=has_cogs,
    )
    if TOTAL_DIMENSION in result.schema:
        result = result.rename({TOTAL_DIMENSION: "segment"})
    internal_columns = [
        column for column in result.columns if column.startswith("_legacy_")
    ]
    if internal_columns:
        result = result.drop(internal_columns)
    return result.sort(
        "total_delta",
        descending=True,
    )


def aggregate_legacy_components(
    leaf: pl.DataFrame,
    report_dimensions: list[str],
    *,
    has_units: bool,
    has_discount: bool,
    has_cogs: bool,
) -> pl.DataFrame:
    """Aggregate bottom-up leaf calculations and recompute pure mix effects."""

    report_df, grouping_dimensions = add_report_total_dimension(leaf, report_dimensions)
    grouped = (
        report_df.lazy()
        .group_by(grouping_dimensions)
        .agg(numeric_sum_expressions(report_df, grouping_dimensions))
        .collect()
    )
    amount0 = pl.col("_legacy_amount0")
    amount1 = pl.col("_legacy_amount1")
    grouped = grouped.with_columns(
        pl.when(amount0 == 0)
        .then(None)
        .otherwise((amount1 - amount0) / amount0 * 100)
        .alias("amount_pct_change")
    )
    if has_units:
        changed_amount0 = pl.col("_legacy_changed_amount0")
        changed_amount1 = pl.col("_legacy_changed_amount1")
        changed_units0 = pl.col("_legacy_changed_units0")
        changed_units1 = pl.col("_legacy_changed_units1")
        pure_changed_volume = legacy_volume_component(
            changed_amount0, changed_amount1, changed_units0, changed_units1
        )
        grouped = grouped.with_columns(
            safe_ratio(amount0, pl.col("_legacy_units0")).alias("price_baseline"),
            safe_ratio(amount1, pl.col("_legacy_units1")).alias("price_comparison"),
            (pure_changed_volume + pl.col("_legacy_new_lost_volume")).alias(
                "volume_variance"
            ),
        )
        grouped = grouped.with_columns(
            (pl.col("_legacy_bottom_up_volume") - pl.col("volume_variance")).alias(
                "mix_variance"
            ),
        )
        grouped = grouped.with_columns(
            (
                pl.col("total_delta")
                - pl.col("price_variance")
                - pl.col("volume_variance")
                - pl.col("mix_variance")
            ).alias("component_reconciliation_delta"),
        )
    if has_discount:
        net0 = amount0 - pl.col("_legacy_discount0")
        net1 = amount1 - pl.col("_legacy_discount1")
        if "discount_variance" in grouped.schema:
            grouped = grouped.with_columns(
                net0.alias("net_baseline"),
                net1.alias("net_comparison"),
                (net1 - net0).alias("net_delta"),
                pl.when(net0 == 0)
                .then(None)
                .otherwise((net1 - net0) / net0 * 100)
                .alias("net_pct_change"),
            )
    if has_cogs:
        discount0 = (
            pl.col("_legacy_discount0")
            if "_legacy_discount0" in grouped.schema
            else pl.lit(0.0)
        )
        discount1 = (
            pl.col("_legacy_discount1")
            if "_legacy_discount1" in grouped.schema
            else pl.lit(0.0)
        )
        cogs0 = pl.col("_legacy_cogs0")
        cogs1 = pl.col("_legacy_cogs1")
        margin0 = amount0 - discount0 - cogs0
        margin1 = amount1 - discount1 - cogs1
        grouped = grouped.with_columns(
            margin0.alias("margin_baseline"),
            margin1.alias("margin_comparison"),
            (margin1 - margin0).alias("margin_delta"),
            pl.when(margin0 == 0)
            .then(None)
            .otherwise((margin1 - margin0) / margin0 * 100)
            .alias("margin_pct_change"),
        )
        if has_units:
            changed_amount0 = pl.col("_legacy_changed_amount0")
            changed_amount1 = pl.col("_legacy_changed_amount1")
            changed_units0 = pl.col("_legacy_changed_units0")
            changed_units1 = pl.col("_legacy_changed_units1")
            changed_discount0 = pl.col("_legacy_changed_discount0")
            changed_discount1 = pl.col("_legacy_changed_discount1")
            changed_cogs0 = pl.col("_legacy_changed_cogs0")
            changed_cogs1 = pl.col("_legacy_changed_cogs1")
            price0 = safe_ratio(changed_amount0, changed_units0)
            price1 = safe_ratio(changed_amount1, changed_units1)
            cost0 = safe_ratio(changed_discount0 + changed_cogs0, changed_units0)
            cost1 = safe_ratio(changed_discount1 + changed_cogs1, changed_units1)
            units_change = changed_units1 - changed_units0
            price_change = price1 - price0
            cost_change = cost1 - cost0
            pure_margin_volume = units_change * (
                price0 - cost0 + price_change / 2 - cost_change / 2
            )
            grouped = grouped.with_columns(
                (pure_margin_volume + pl.col("_legacy_new_lost_margin_volume")).alias(
                    "margin_volume_variance"
                )
            )
            grouped = grouped.with_columns(
                (
                    pl.col("_legacy_bottom_up_margin_volume")
                    - pl.col("margin_volume_variance")
                ).alias("margin_mix_variance"),
            )
            margin_component_sum = (
                pl.col("margin_price_variance")
                + pl.col("margin_volume_variance")
                + pl.col("margin_mix_variance")
            )
            if "discount_variance" in grouped.schema:
                margin_component_sum = margin_component_sum + pl.col(
                    "discount_variance"
                )
            if "cogs_variance" in grouped.schema:
                margin_component_sum = margin_component_sum + pl.col("cogs_variance")
            grouped = grouped.with_columns(
                (pl.col("margin_delta") - margin_component_sum).alias(
                    "margin_component_reconciliation_delta"
                )
            )
    return grouped


def bridge_dimension_sets(dimensions: list[str], enabled: bool) -> list[list[str]]:
    """Return dimension combinations for root-cause variance output."""

    if not enabled or len(dimensions) < 2:
        return []
    return [
        list(combo)
        for size in range(1, len(dimensions) + 1)
        for combo in itertools.combinations(dimensions, size)
    ]


def write_outputs(
    result: pl.DataFrame,
    audit: dict[str, Any],
    summary: str,
    output_dir: Path,
    *,
    artifact_paths: list[str],
) -> None:
    """Write deterministic variance outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    result.write_csv(output_dir / "variance_results.csv")
    try:
        result.write_excel(output_dir / "variance_results.xlsx")
        audit["outputs"]["variance_results.xlsx"] = "written"
    except (ImportError, ModuleNotFoundError, OSError, ValueError) as exc:
        audit["outputs"]["variance_results.xlsx"] = f"not_written: {exc}"
    write_json(output_dir / "variance_audit.json", audit)
    (output_dir / "variance_summary.md").write_text(summary, encoding="utf-8")
    audit["outputs"]["variance_results.csv"] = "written"
    audit["outputs"]["variance_audit.json"] = "written"
    audit["outputs"]["variance_summary.md"] = "written"
    for path in artifact_paths:
        audit["outputs"][Path(path).name] = "written"
    write_json(output_dir / "variance_audit.json", audit)


def _relative_artifact_path(path: Path, base: Path) -> str:
    """Return a stable artifact path relative to ``base`` when possible."""

    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _artifact_kind(path: Path) -> str:
    """Return the artifact group for a generated file."""

    suffix = path.suffix.lower()
    if suffix in {".png", ".html", ".htm"}:
        return "charts"
    if suffix in {".csv", ".xlsx"}:
        return "tables"
    if suffix == ".json":
        return "contexts"
    if suffix == ".md":
        return "briefs"
    if suffix == ".docx":
        return "reports"
    return "files"


def _chart_type_from_name(name: str) -> str:
    """Return a stable chart type from a generated PNG name."""

    stem = Path(name).stem
    if stem == "waterfall":
        return "standard_variance_waterfall"
    if stem == "waterfall_small_multiples":
        return "standard_variance_small_multiples"
    if stem == "total_by_dimension_bridge":
        return "total_by_dimension_bridge"
    if stem == "exploded_variance_bridge":
        return "exploded_variance_bridge"
    if stem == "pvm_decomposition_ladder":
        return "pvm_decomposition_ladder"
    if stem.startswith("root_cause_client_report_"):
        return "client_report_chart"
    if stem.startswith("root_cause_component_bridge"):
        return "root_cause_component_bridge"
    if stem.startswith("root_cause_total_bridge"):
        return "root_cause_total_bridge"
    if "drilldown" in stem:
        return "root_cause_drilldown"
    if stem.startswith("root_cause_bridge_alt_"):
        return "root_cause_alternative_bridge"
    if stem.startswith("root_cause_bridge"):
        return "root_cause_bridge"
    return "chart"


def _root_cause_bridge_variant(stem: str) -> str | None:
    """Return the formal root-cause bridge variant for a generated artifact."""

    if stem.startswith("root_cause_bridge_alt_") and "drilldown" in stem:
        return "alternative_drilldown"
    if stem.startswith("root_cause_bridge_alt_"):
        return "alternative_sequence"
    if stem == "root_cause_component_bridge":
        return "component_sequence"
    if stem == "root_cause_total_bridge":
        return "main_sequence"
    if "drilldown" in stem:
        return "drilldown"
    if stem == "root_cause_bridge_moved_rows":
        return "moved_rows"
    if stem == "root_cause_bridge":
        return "main_sequence"
    return None


def _root_cause_alternative_result(stem: str) -> int | None:
    """Return the legacy alternative number embedded in a root-cause artifact."""

    prefix = "root_cause_bridge_alt_"
    if not stem.startswith(prefix):
        return None
    candidate = stem.removeprefix(prefix).split("_", 1)[0]
    return int(candidate) if candidate.isdecimal() else None


def _root_cause_drilldown_row(stem: str) -> int | None:
    """Return the parent row number embedded in a root-cause drilldown artifact."""

    marker = "_drilldown_row_"
    if marker not in stem:
        return None
    candidate = stem.split(marker, 1)[1].split("_", 1)[0]
    return int(candidate) if candidate.isdecimal() else None


def _root_cause_parent_artifact_id(stem: str) -> str | None:
    """Return the parent sequence artifact id for a root-cause drilldown."""

    drilldown_row = _root_cause_drilldown_row(stem)
    if drilldown_row is None:
        return None
    alternative_result = _root_cause_alternative_result(stem)
    if alternative_result is not None:
        return f"root_cause_bridge_alt_{alternative_result}"
    if stem.startswith("root_cause_total_bridge_drilldown_row_"):
        return "root_cause_total_bridge"
    if stem.startswith("root_cause_bridge_drilldown_row_"):
        return "root_cause_bridge"
    return None


def _root_cause_bridge_frame_identity(source: Path) -> dict[str, Any]:
    """Return the analytical row sequence behind a root-cause bridge artifact."""

    bridge_path = source.with_suffix(".csv")
    if not bridge_path.exists():
        return {}
    try:
        frame = _collect_csv_scan(bridge_path, separator=",")
    except (OSError, pl.exceptions.PolarsError):
        return {}
    dimensions = _root_cause_dimension_columns(frame)
    sequence: list[dict[str, Any]] = []
    for index, row in enumerate(frame.to_dicts(), start=1):
        filters = {
            dimension: row.get(dimension)
            for dimension in dimensions
            if row.get(dimension) not in (None, "", "All")
        }
        sequence.append(
            {
                "row_number": index,
                "bridge_level": row.get("bridge_level"),
                "bridge_dimensions": row.get("bridge_dimensions"),
                "filters": filters,
                "variance_type": row.get("variance_type"),
                "variance_amount": float(row.get("variance_amount") or 0.0),
            }
        )
    variant = _root_cause_bridge_variant(source.stem)
    alternative_result = _root_cause_alternative_result(source.stem)
    drilldown_row = _root_cause_drilldown_row(source.stem)
    identity = {
        "root_cause_bridge_variant": _root_cause_bridge_variant(source.stem),
        "alternative_result": alternative_result,
        "drilldown_row": drilldown_row,
        "root_cause_sequence": sequence,
    }
    parent_artifact_id = _root_cause_parent_artifact_id(source.stem)
    if parent_artifact_id is not None:
        identity["parent_artifact_id"] = parent_artifact_id
        identity["parent_row_number"] = drilldown_row
    if variant == "alternative_drilldown":
        identity["child_artifact_type"] = "alternative_drilldown"
        identity["parent_capability_id"] = "variance.root_cause_alternative_sweep"
        identity["parent_child_type"] = "alternative_sequence"
        identity["parent_alternative_result"] = alternative_result
    return identity


def _total_by_dimension_bridge_frame_identity(source: Path) -> dict[str, Any]:
    """Return the analytical row sequence behind a total-by-dimension chart."""

    bridge_path = source.with_suffix(".csv")
    if not bridge_path.exists():
        return {}
    try:
        frame = _collect_csv_scan(bridge_path, separator=",")
    except (OSError, pl.exceptions.PolarsError):
        return {}
    if frame.is_empty() or "dimension_value" not in frame.columns:
        return {}
    first_dimension = (
        str(frame["dimension"][0]) if "dimension" in frame.columns else None
    )
    sequence: list[dict[str, Any]] = []
    for row in frame.to_dicts():
        sequence.append(
            {
                "row_number": row.get("row_number"),
                "dimension_value": row.get("dimension_value"),
                "row_type": row.get("row_type"),
                "amount_baseline": float(row.get("amount_baseline") or 0.0),
                "amount_comparison": float(row.get("amount_comparison") or 0.0),
                "total_delta": float(row.get("total_delta") or 0.0),
                "percent_delta": (
                    float(row["percent_delta"])
                    if row.get("percent_delta") is not None
                    else None
                ),
            }
        )
    identity: dict[str, Any] = {
        "total_by_dimension_bridge_dimension": first_dimension,
        "total_by_dimension_sequence": sequence,
    }
    return identity


def _exploded_variance_bridge_identity(source: Path) -> dict[str, Any]:
    """Return the native parent/child bridge identity from its spec sidecar."""

    spec_path = source.with_name("exploded_variance_bridge_spec.json")
    if not spec_path.exists():
        return {}
    try:
        payload = load_json(spec_path)
    except (OSError, json.JSONDecodeError):
        return {}
    selection = payload.get("selection") or {}
    parent = payload.get("parent") or {}
    children = payload.get("children") or []
    return {
        "exploded_variance_bridge_parent_dimension": selection.get("parent_dimension"),
        "exploded_variance_bridge_child_dimension": selection.get("child_dimension"),
        "exploded_variance_bridge_max_drilldowns": selection.get("max_drilldowns"),
        "exploded_variance_bridge_parent_rows": parent.get("rows") or [],
        "exploded_variance_bridge_drilldowns": [
            {
                "drilldown_id": child.get("drilldown_id"),
                "parent_row_number": child.get("parent_row_number"),
                "parent_dimension_value": child.get("parent_dimension_value"),
                "child_dimension": child.get("child_dimension"),
                "rows": child.get("rows") or [],
            }
            for child in children
        ],
    }


def _movement_driver_dimension(
    chart_type: str,
    recipe: dict[str, Any],
) -> str | list[str] | None:
    """Return the deterministic driver dimension represented by a variance chart."""

    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    if chart_type == "standard_variance_waterfall":
        return "variance_component"
    if chart_type == "standard_variance_small_multiples":
        return options.get("waterfall_small_multiples_dimension")
    if chart_type == "total_by_dimension_bridge":
        return options.get("total_by_dimension_bridge_dimension")
    if chart_type == "exploded_variance_bridge":
        return [
            value
            for value in [
                options.get("exploded_variance_bridge_parent_dimension"),
                options.get("exploded_variance_bridge_child_dimension"),
            ]
            if value
        ]
    if chart_type == "pvm_decomposition_ladder":
        return "pvm_component"
    if chart_type.startswith("root_cause"):
        dimensions = mappings.get("dimensions") or []
        return [str(value) for value in dimensions] if dimensions else "root_cause"
    return None


def _normalize_artifact_mode(artifact_mode: str) -> str:
    """Return a supported artifact mode or raise for invalid contract input."""

    normalized = str(artifact_mode or ARTIFACT_MODE_DATA_AND_RENDER).strip().lower()
    if normalized not in ARTIFACT_MODES:
        allowed = ", ".join(sorted(ARTIFACT_MODES))
        raise ValueError(f"Unsupported artifact_mode {artifact_mode!r}; use {allowed}.")
    return normalized


def _variance_data_chart_enabled(
    chart_type: str,
    available_chart_types: Sequence[str],
) -> bool:
    return chart_type in set(available_chart_types)


def _variance_chart_selected(
    chart_type: str,
    artifact_mode: str,
    available_chart_types: Sequence[str],
) -> bool:
    if chart_type not in set(available_chart_types):
        return False
    return artifact_mode != ARTIFACT_MODE_DATA_ONLY


def _data_written_chart_audit(
    *,
    chart_type: str,
    artifact_name: str,
    source_functions: Sequence[str],
) -> dict[str, Any]:
    return {
        "status": "data_written",
        "artifact": artifact_name,
        "rendered": False,
        "source_functions": list(source_functions),
        "chart_type": chart_type,
    }


def _skipped_chart_audit(chart_type: str, reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "chart_type": chart_type,
        "reason": reason,
    }


def _comparison_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return comparison metadata for reporting agents."""

    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    return {
        "baseline": mappings.get("baseline_period"),
        "comparison": mappings.get("comparison_period"),
        "basis": options.get("comparison_basis"),
        "mode": options.get("period_comparison_mode"),
        "period_window": options.get("period_window"),
    }


def _title_contract_payload(
    recipe: dict[str, Any],
    *,
    chart_kind: str,
    dimension: str | None = None,
) -> dict[str, Any]:
    """Return the visible three-row title contract for a variance chart."""

    title = build_ibcs_title(recipe, chart_kind=chart_kind, dimension=dimension)
    return {
        "chart_title_lines": title.lines(),
        "title_contract": {
            "who": title.who,
            "what": title.what,
            "when": title.when,
        },
    }


def _standard_variance_context(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Return data context behind the standard variance chart."""

    components = [
        {
            "variance_type": label,
            "variance_amount": _numeric_column_sum(result, column),
            "source_column": column,
            "is_residual_other": False,
        }
        for label, column in standard_variance_component_columns(recipe)
    ]
    total_delta = _numeric_column_sum(result, "total_delta")
    component_sum = sum(float(item["variance_amount"] or 0.0) for item in components)
    residual = total_delta - component_sum
    components.append(
        {
            "variance_type": "Other",
            "variance_amount": residual,
            "source_column": "component_reconciliation_delta",
            "is_residual_other": True,
        }
    )
    dominant = _dominant_component(components)
    mappings = recipe.get("mappings") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "chart_id": "standard_variance_waterfall",
        "chart_family": "variance_analysis",
        "chart_type": "standard_variance_waterfall",
        "chart_path": (
            "charts/waterfall.png" if (output_dir / "waterfall.png").exists() else None
        ),
        "metric": mappings.get("amount_column"),
        "unit": (recipe.get("options") or {}).get("currency") or "EUR",
        "comparison": _comparison_payload(recipe),
        "recipe_filters": (recipe.get("options") or {}).get("recipe_filter_audit"),
        "recipe_cohorts": (recipe.get("options") or {}).get("recipe_cohort_audit"),
        "dimensions": mappings.get("dimensions") or [],
        "calculation_grain": mappings.get("calculation_grain") or [],
        **_title_contract_payload(recipe, chart_kind="standard_variance"),
        "totals": {
            "amount_baseline": _numeric_column_sum(result, "amount_baseline"),
            "amount_comparison": _numeric_column_sum(result, "amount_comparison"),
            "total_delta": total_delta,
            "component_sum": component_sum,
            "other_residual": residual,
        },
        "components": components,
        "dominant_component": {
            "variance_type": dominant.get("variance_type"),
            "variance_amount": dominant.get("variance_amount"),
        },
        "top_rows_by_abs_delta": top_driver_rows(result, limit=10),
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "required_points": [
                "Explain the dominant standard variance component.",
                "State whether Other/residual is material.",
                "Use small-multiples context when available before claiming concentration or spread.",
                "Distinguish deterministic variance facts from business interpretation.",
            ],
        },
    }


def _pvm_ladder_levels(
    result: pl.DataFrame,
    recipe: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the structured chart data behind the PVM decomposition ladder."""

    total_delta = _numeric_column_sum(result, "total_delta")
    price = _numeric_column_sum(result, "price_variance")
    volume = _numeric_column_sum(result, "volume_variance")
    mix = _numeric_column_sum(result, "mix_variance")
    residual = total_delta - price - volume - mix
    unit_label = "Units" if recipe["mappings"].get("units_column") else "Volume"
    return [
        {
            "level": 1,
            "calculation": f"Price & {unit_label.lower()} & mix",
            "components": [
                {
                    "variance_type": f"Price & {unit_label.lower()} & mix",
                    "variance_amount": total_delta,
                    "source_columns": ["total_delta"],
                    "is_residual_other": False,
                }
            ],
        },
        {
            "level": 2,
            "calculation": f"Price, {unit_label.lower()} & mix",
            "components": [
                {
                    "variance_type": "Price",
                    "variance_amount": price,
                    "source_columns": ["price_variance"],
                    "is_residual_other": False,
                },
                {
                    "variance_type": f"{unit_label} & mix",
                    "variance_amount": total_delta - price,
                    "source_columns": [
                        "volume_variance",
                        "mix_variance",
                        "component_reconciliation_delta",
                    ],
                    "is_residual_other": False,
                },
            ],
        },
        {
            "level": 3,
            "calculation": f"Price, {unit_label.lower()}, mix",
            "components": [
                {
                    "variance_type": "Price",
                    "variance_amount": price,
                    "source_columns": ["price_variance"],
                    "is_residual_other": False,
                },
                {
                    "variance_type": unit_label,
                    "variance_amount": volume,
                    "source_columns": ["volume_variance"],
                    "is_residual_other": False,
                },
                {
                    "variance_type": "Mix",
                    "variance_amount": mix,
                    "source_columns": ["mix_variance"],
                    "is_residual_other": False,
                },
                {
                    "variance_type": "Other",
                    "variance_amount": residual,
                    "source_columns": ["component_reconciliation_delta"],
                    "is_residual_other": True,
                },
            ],
        },
    ]


def _pvm_decomposition_ladder_context(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Return model-facing context for the PVM decomposition ladder."""

    levels = _pvm_ladder_levels(result, recipe)
    totals = {
        "amount_baseline": _numeric_column_sum(result, "amount_baseline"),
        "amount_comparison": _numeric_column_sum(result, "amount_comparison"),
        "total_delta": _numeric_column_sum(result, "total_delta"),
        "price_variance": _numeric_column_sum(result, "price_variance"),
        "volume_variance": _numeric_column_sum(result, "volume_variance"),
        "mix_variance": _numeric_column_sum(result, "mix_variance"),
        "component_reconciliation_delta": _numeric_column_sum(
            result, "component_reconciliation_delta"
        ),
    }
    baseline_total = float(totals["amount_baseline"] or 0.0)
    totals["delta_percent"] = (
        (float(totals["total_delta"] or 0.0) / baseline_total) * 100
        if abs(baseline_total) > TOLERANCE
        else None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "chart_id": "pvm_decomposition_ladder",
        "chart_family": "variance_analysis",
        "chart_type": "pvm_decomposition_ladder",
        "chart_path": (
            "charts/pvm_decomposition_ladder.png"
            if (output_dir / "pvm_decomposition_ladder.png").exists()
            else None
        ),
        "metric": (recipe.get("mappings") or {}).get("amount_column"),
        "unit": (recipe.get("options") or {}).get("currency") or "EUR",
        "comparison": _comparison_payload(recipe),
        **_title_contract_payload(recipe, chart_kind="pvm_decomposition_ladder"),
        "levels": levels,
        "totals": totals,
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "purpose": (
                "Compare the same total variance under progressively richer "
                "Price / Units / Mix decompositions before deciding which "
                "breakdown is useful for the client story."
            ),
            "required_points": [
                "State whether the one-line total variance hides offsetting components.",
                "Explain what changes when Price is separated from Units & Mix.",
                "Explain what changes when Units and Mix are separated.",
                "Mention Other only when the reconciliation residual is material.",
            ],
        },
    }


def write_pvm_decomposition_ladder_chart_data(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
) -> tuple[list[str], dict[str, Any], str]:
    """Write CSV and JSON data for the PVM decomposition ladder."""

    if not bool(recipe.get("options", {}).get("pvm_decomposition_ladder", True)):
        return [], {"status": "disabled"}, ""
    if not recipe.get("mappings", {}).get("units_column"):
        return (
            [],
            {
                "status": "not_written_missing_units",
                "reason": "PVM decomposition ladder requires a units column.",
            },
            "",
        )
    context = _pvm_decomposition_ladder_context(result, recipe, output_dir)
    context_path = output_dir / "pvm_decomposition_ladder_context.json"
    write_json(context_path, context)
    rows = []
    for level in context["levels"]:
        for component in level["components"]:
            rows.append(
                {
                    "level": level["level"],
                    "calculation": level["calculation"],
                    "variance_type": component["variance_type"],
                    "variance_amount": component["variance_amount"],
                    "is_residual_other": component["is_residual_other"],
                    "source_columns": " | ".join(component["source_columns"]),
                }
            )
    table_path = output_dir / "pvm_decomposition_ladder.csv"
    pl.DataFrame(rows).write_csv(table_path)
    summary = [
        "",
        "## PVM Decomposition Ladder",
        "",
        (
            "This chart compares the same total variance at three calculation "
            "depths: combined Price/Units/Mix, Price plus Units & Mix, and "
            "Price/Units/Mix separately."
        ),
        "",
    ]
    for level in context["levels"]:
        components = ", ".join(
            f"{item['variance_type']} `{float(item['variance_amount']):,.2f}`"
            for item in level["components"]
            if abs(float(item["variance_amount"] or 0.0)) > TOLERANCE
        )
        summary.append(
            f"- Level {level['level']} `{level['calculation']}`: {components}"
        )
    return (
        [str(table_path), str(context_path)],
        {
            "status": "written",
            "table": table_path.name,
            "context": context_path.name,
            "level_count": len(context["levels"]),
            "component_row_count": len(rows),
        },
        "\n".join(summary) + "\n",
    )


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file when present and valid."""

    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def max_abs(df: pl.DataFrame, column: str) -> float | None:
    """Return the maximum absolute value for a column when it exists."""

    if column not in df.schema or df.is_empty():
        return None
    value = df.select(pl.col(column).abs().max()).item()
    return float(value) if value is not None else None


def build_audit(
    input_path: Path,
    recipe: dict[str, Any],
    result: pl.DataFrame,
    artifact_paths: list[str],
) -> dict[str, Any]:
    """Build audit metadata for a variance run."""

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_file": str(input_path),
        "row_count": result.height,
        "recipe": recipe,
        "checks": {
            "max_abs_component_reconciliation_delta": max_abs(
                result, "component_reconciliation_delta"
            ),
            "max_abs_margin_reconciliation_delta": max_abs(
                result, "margin_mix_variance"
            ),
            "max_abs_margin_component_reconciliation_delta": max_abs(
                result, "margin_component_reconciliation_delta"
            ),
        },
        "outputs": {Path(path).name: "written" for path in artifact_paths},
    }


def top_driver_rows(result: pl.DataFrame, limit: int = 10) -> list[dict[str, Any]]:
    """Return top variance rows by absolute total delta."""

    if result.is_empty():
        return []
    return (
        result.with_columns(pl.col("total_delta").abs().alias("_abs_delta"))
        .sort("_abs_delta", descending=True)
        .drop("_abs_delta")
        .head(limit)
        .to_dicts()
    )


def build_summary_markdown(result: pl.DataFrame, recipe: dict[str, Any]) -> str:
    """Build deterministic markdown for Codex to interpret."""

    mappings = recipe["mappings"]
    options = recipe.get("options") or {}
    lines = [
        "# Variance Analysis Source Data",
        "",
        f"- Comparison basis: `{options.get('comparison_basis') or 'unknown'}`",
        f"- Period comparison mode: `{options.get('period_comparison_mode') or 'unknown'}`",
        f"- Baseline period: `{mappings['baseline_period']}`",
        f"- Comparison period: `{mappings['comparison_period']}`",
        f"- Amount column: `{mappings['amount_column']}`",
        f"- Dimensions: `{', '.join(mappings.get('dimensions') or ['Total'])}`",
        f"- Calculation grain: `{', '.join(mappings.get('calculation_grain') or mappings.get('dimensions') or ['Total'])}`",
        f"- Result rows: `{result.height}`",
        "",
        "## Totals",
        "",
    ]
    period_window = options.get("period_window") or {}
    if period_window:
        baseline = period_window.get("baseline", {})
        comparison = period_window.get("comparison", {})
        lines[7:7] = [
            f"- Date column: `{period_window.get('date_column')}`",
            (
                "- Baseline date window: "
                f"`{baseline.get('start_date')}` to `{baseline.get('end_date')}`"
            ),
            (
                "- Comparison date window: "
                f"`{comparison.get('start_date')}` to `{comparison.get('end_date')}`"
            ),
        ]
    totals = result.select(
        [
            pl.col("total_delta").sum().alias("total_delta"),
            *[
                pl.col(column).sum().alias(column)
                for column in (
                    "price_variance",
                    "volume_variance",
                    "mix_variance",
                    "net_delta",
                    "margin_delta",
                    "cogs_delta",
                )
                if column in result.schema
            ],
        ]
    ).to_dicts()[0]
    for key, value in totals.items():
        lines.append(
            f"- `{key}`: {value:,.2f}"
            if isinstance(value, (int, float))
            else f"- `{key}`: {value}"
        )
    lines.extend(["", "## Largest Absolute Drivers", ""])
    for row in top_driver_rows(result, 10):
        dims = [
            f"{dimension}={row.get(dimension)}"
            for dimension in mappings.get("dimensions") or ["segment"]
            if dimension in row
        ]
        label = ", ".join(dims) if dims else "Total"
        delta = row.get("total_delta")
        lines.append(f"- {label}: total_delta={float(delta):,.2f}")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "The figures above are deterministic calculations. Codex should use them as source data, identify the largest drivers, call out missing mappings or zero-denominator caveats, and avoid changing deterministic results silently.",
        ]
    )
    return "\n".join(lines) + "\n"


def append_bridge_dimension_summary(
    summary: str, bridge_audit: dict[str, Any] | None
) -> str:
    """Append requested-versus-emitted root-cause dimensions to the summary."""

    if not bridge_audit or not bridge_audit.get("enabled"):
        return summary

    def formatted(values: Any) -> str:
        if not values:
            return "`none`"
        return "`" + ", ".join(values) + "`"

    lines = [
        "",
        "## Root-Cause Variance Analysis",
        "",
        "- Requested report dimensions: "
        f"{formatted(bridge_audit.get('requested_report_dimensions'))}",
        "- Requested calculation grain: "
        f"{formatted(bridge_audit.get('requested_calculation_grain'))}",
        "- Effective root-cause dimensions: "
        f"{formatted(bridge_audit.get('effective_bridge_dimensions'))}",
        "- Emitted root-cause dimensions: "
        f"{formatted(bridge_audit.get('emitted_bridge_dimensions'))}",
        "- Dropped root-cause dimensions: "
        f"{formatted(bridge_audit.get('dropped_bridge_dimensions'))}",
        "- Internally added root-cause dimensions: "
        f"{formatted(bridge_audit.get('internally_added_bridge_dimensions'))}",
    ]
    return summary.rstrip() + "\n" + "\n".join(lines) + "\n"


def _root_cause_dimension_columns(frame: pl.DataFrame) -> list[str]:
    """Return active dimension columns in a normalized root-cause bridge frame."""

    return [
        column
        for column in frame.columns
        if column not in ROOT_CAUSE_BRIDGE_MEASURE_COLUMNS
    ]


def _root_cause_row_label(row: dict[str, Any], dimensions: list[str]) -> str:
    """Return a compact business label for a selected root-cause row."""

    inactive_values = {"", "All", "N/A", "None", "null"}
    values = [
        str(row.get(dimension))
        for dimension in dimensions
        if row.get(dimension) is not None
        and str(row.get(dimension)) not in inactive_values
    ]
    label = " / ".join(values) if values else "Total"
    variance_type = row.get("variance_type")
    if variance_type is not None and str(variance_type):
        label = f"{label} - {variance_type}"
    return label


def _root_cause_total_delta(result: pl.DataFrame) -> float:
    """Return the overall comparison minus baseline delta for bridge residuals."""

    if result.is_empty():
        return 0.0
    values = result.select(
        (pl.col("amount_comparison").sum() - pl.col("amount_baseline").sum()).alias(
            "total_delta"
        )
    ).to_dicts()[0]
    return float(values["total_delta"] or 0.0)


def _root_cause_selected_sum(frame: pl.DataFrame) -> float:
    """Return the selected legacy sequence variance sum."""

    if frame.is_empty() or "variance_amount" not in frame.schema:
        return 0.0
    value = frame.select(pl.col("variance_amount").sum()).item()
    return float(value or 0.0)


def _root_cause_sequence_payload(
    *,
    alternative_result: int,
    frame: pl.DataFrame,
    audit: dict[str, Any],
    result: pl.DataFrame,
    bridge_path: Path | None,
    chart_path: Path | None,
) -> dict[str, Any]:
    """Return model-facing metadata for one root-cause alternative."""

    dimensions = _root_cause_dimension_columns(frame)
    rows = [
        {
            "row_number": index + 1,
            "label": _root_cause_row_label(row, dimensions),
            "variance_amount": float(row.get("variance_amount") or 0.0),
            "bridge_dimensions": row.get("bridge_dimensions"),
            "variance_type": row.get("variance_type"),
        }
        for index, row in enumerate(frame.to_dicts())
    ]
    drilldown_row_numbers: list[int] = []
    for audit_key in ("drilldown_requested_rows", "automatic_drilldown_rows"):
        for value in audit.get(audit_key, []) or []:
            try:
                row_number = int(value)
            except (TypeError, ValueError):
                continue
            if row_number > 0 and row_number not in drilldown_row_numbers:
                drilldown_row_numbers.append(row_number)
    child_artifacts = []
    for row_number in drilldown_row_numbers:
        parent_row = rows[row_number - 1] if row_number <= len(rows) else {}
        child_artifacts.append(
            {
                "child_type": "alternative_drilldown",
                "capability_id": "variance.root_cause_alternative_sweep",
                "parent_capability_id": "variance.root_cause_alternative_sweep",
                "parent_child_type": "alternative_sequence",
                "parent_artifact_id": f"root_cause_bridge_alt_{alternative_result}",
                "alternative_result": alternative_result,
                "drilldown_row": row_number,
                "parent_row_number": row_number,
                "parent_row_label": parent_row.get("label", ""),
                "parent_row_bridge_dimensions": parent_row.get("bridge_dimensions"),
                "parent_row_variance_type": parent_row.get("variance_type"),
                "parent_row_variance_amount": parent_row.get("variance_amount"),
                "artifact_id": (
                    f"root_cause_bridge_alt_{alternative_result}"
                    f"_drilldown_row_{row_number}"
                ),
                "chart_artifact": (
                    f"root_cause_bridge_alt_{alternative_result}"
                    f"_drilldown_row_{row_number}.png"
                ),
                "table_artifact": (
                    f"root_cause_bridge_alt_{alternative_result}"
                    f"_drilldown_row_{row_number}.csv"
                ),
            }
        )
    total_delta = _root_cause_total_delta(result)
    selected_sum = _root_cause_selected_sum(frame)
    return {
        "alternative_result": alternative_result,
        "row_count": frame.height,
        "selected_rows": rows,
        "selected_sequence_bridge_dimensions": audit.get(
            "selected_sequence_bridge_dimensions", []
        ),
        "selected_sequence_unique_bridge_dimensions": audit.get(
            "selected_sequence_unique_bridge_dimensions", []
        ),
        "selected_sequence_has_mixed_dimensions": bool(
            audit.get("selected_sequence_has_mixed_dimensions", False)
        ),
        "total_delta": total_delta,
        "selected_sequence_sum": selected_sum,
        "other_residual": total_delta - selected_sum,
        "drilldown_status": audit.get("drilldown_status"),
        "drilldown_requested_rows": audit.get("drilldown_requested_rows", []),
        "automatic_drilldown_mode": audit.get("automatic_drilldown_mode", "none"),
        "automatic_drilldown_rows": audit.get("automatic_drilldown_rows", []),
        "child_artifacts": child_artifacts,
        "bridge_path": str(bridge_path) if bridge_path else "",
        "chart_path": str(chart_path) if chart_path else "",
    }


def _root_cause_resolved_parameters(
    recipe: dict[str, Any],
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Return the formal request parameters resolved by the root-cause runtime."""

    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    return {
        key: json_safe(value)
        for key, value in {
            "metric": mappings.get("amount_column"),
            "units_metric": mappings.get("units_column"),
            "comparison_basis": options.get("comparison_basis"),
            "baseline_period": mappings.get("baseline_period"),
            "comparison_period": mappings.get("comparison_period"),
            "period_column": mappings.get("period_column"),
            "date_column": mappings.get("date_column"),
            "dimensions": mappings.get("dimensions") or [],
            "calculation_grain": mappings.get("calculation_grain") or [],
            "effective_bridge_dimensions": audit.get("effective_bridge_dimensions"),
            "emitted_bridge_dimensions": audit.get("emitted_bridge_dimensions"),
            "dropped_bridge_dimensions": audit.get("dropped_bridge_dimensions"),
            "alternative_result": audit.get("alternative_result"),
            "filters": options.get("recipe_filter_audit")
            or recipe.get("filters")
            or options.get("filters"),
            "population_preparation": options.get("recipe_cohort_audit")
            or options.get("cohort_definition")
            or recipe.get("cohorts")
            or options.get("cohorts"),
        }.items()
        if value is not None and value != "" and value != [] and value != {}
    }


def _write_root_cause_bridge_context(
    *,
    frame: pl.DataFrame,
    result: pl.DataFrame,
    recipe: dict[str, Any],
    audit: dict[str, Any],
    output_dir: Path,
    bridge_path: Path,
    chart_path: Path | None,
    context_name: str = "root_cause_total_bridge_context.json",
    analysis_type: str = "root_cause_total_bridge",
    capability_id: str = "variance.root_cause_total_bridge",
    chart_type: str = "root_cause_total_bridge",
) -> Path:
    """Write the structured payload behind the main root-cause bridge."""

    variance_mode = str(audit.get("root_cause_variance_mode") or "total_variance")
    if variance_mode == "component_variance":
        deterministic_boundary = (
            "The plugin selected and reconciled component-by-dimension rows. "
            "Codex may interpret whether the component bridge is useful, but "
            "must not change calculated rows, component types, amounts, "
            "dimensions, or residuals."
        )
        required_points = [
            "Treat this as second-order diagnostic source data.",
            "Read each row as a variance component for a selected slice.",
            "Do not describe component rows as having meaningful initial/final row bars.",
            "Do not invent causes outside the generated component rows.",
        ]
    else:
        deterministic_boundary = (
            "The plugin selected and reconciled total-variance root-cause rows. "
            "Codex may interpret whether the bridge is useful, but must not "
            "change calculated rows, amounts, dimensions, or residuals."
        )
        required_points = [
            "State that each selected row is total variance for that slice.",
            "Use baseline and comparison row values where they are present.",
            "Call out when a selected sequence mixes dimensions.",
            "Use generated drilldown artifacts only when they exist.",
            "Do not invent causes outside the generated bridge rows.",
        ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "analysis_type": analysis_type,
        "capability_id": capability_id,
        "chart_family": "variance_analysis",
        "chart_type": chart_type,
        "root_cause_variance_mode": variance_mode,
        "metric": (recipe.get("mappings") or {}).get("amount_column"),
        "comparison": _comparison_payload(recipe),
        "resolved_parameters": _root_cause_resolved_parameters(recipe, audit),
        "main_sequence": _root_cause_sequence_payload(
            alternative_result=int(audit.get("alternative_result") or 1),
            frame=frame,
            audit=audit,
            result=result,
            bridge_path=bridge_path,
            chart_path=chart_path,
        ),
        "runtime_audit": {
            "variable_bridge_source": audit.get("variable_bridge_source"),
            "legacy_processing_choice": audit.get("legacy_processing_choice"),
            "legacy_variance_aggregation": audit.get("legacy_variance_aggregation"),
            "plugin_variance_aggregation": audit.get("plugin_variance_aggregation"),
            "root_cause_variance_mode": audit.get("root_cause_variance_mode"),
            "selected_sequence_has_mixed_dimensions": audit.get(
                "selected_sequence_has_mixed_dimensions"
            ),
            "selected_sequence_unique_bridge_dimensions": audit.get(
                "selected_sequence_unique_bridge_dimensions"
            ),
            "drilldown_status": audit.get("drilldown_status"),
            "moved_rows_status": audit.get("moved_rows_status"),
            "alternative_sweep_enabled": audit.get("alternative_sweep_enabled"),
            "alternative_sweep_values": audit.get("alternative_sweep_values"),
        },
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "deterministic_boundary": deterministic_boundary,
            "required_points": required_points,
        },
    }
    context_path = output_dir / context_name
    write_json(context_path, payload)
    return context_path


def _root_cause_sweep_interpretation_contract() -> dict[str, Any]:
    """Return the model-facing contract for root-cause sweep interpretation."""

    return {
        "codex_output_file": "codex_root_cause_sweep_analysis.md",
        "deterministic_boundary": (
            "The plugin has already selected and reconciled the alternatives. "
            "Codex may interpret, compare, and recommend drilldowns, but must "
            "not change calculated rows, amounts, dimensions, or residuals."
        ),
        "required_interpretation_points": [
            "Separate deterministic facts from business interpretation.",
            "Identify which alternatives are genuinely mixed-dimension.",
            "Explain that each row is residual after earlier selected rows.",
            "Rank alternatives as useful, possibly useful, or misleading/noisy.",
            "Recommend drilldowns only from generated rows and detail outputs.",
            "State caveats where labels, currency assumptions, units, or hierarchy meaning are missing.",
        ],
        "forbidden_claims": [
            "Do not describe same-dimension alternatives as mixed variable-dimension bridges.",
            "Do not interpret a later mixed row as the total for that dimension.",
            "Do not fabricate rows or causes that are not in the generated files.",
        ],
    }


def _format_root_cause_brief_amount(value: Any) -> str:
    """Format a root-cause amount for a markdown interpretation brief."""

    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return str(value)


def _root_cause_sweep_interpretation_brief(
    *,
    context_payload: dict[str, Any],
    summary_rows: list[dict[str, Any]],
) -> str:
    """Return a Codex-facing markdown brief for root-cause sweep analysis."""

    contract = context_payload["codex_interpretation_contract"]
    lines = [
        "# Codex Root-Cause Sweep Interpretation Brief",
        "",
        "This file is a model-facing handoff. The figures are deterministic; the narrative interpretation is Codex's job.",
        "",
        "## Output To Write",
        "",
        f"- Write: `{contract['codex_output_file']}`",
        "- Use: `root_cause_sweep_model_context.json`, `root_cause_sweep_summary.csv`, and the generated `root_cause_bridge_alt_<n>.png` charts.",
        "",
        "## Interpretation Boundary",
        "",
        f"- {contract['deterministic_boundary']}",
        "- Later rows are residual after earlier selected rows, not standalone totals for that dimension.",
        "",
        "## Required Analysis",
        "",
    ]
    lines.extend(f"- {item}" for item in contract["required_interpretation_points"])
    lines.extend(
        [
            "",
            "## Forbidden Claims",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in contract["forbidden_claims"])
    lines.extend(
        [
            "",
            "## Alternative Overview",
            "",
            "| Alternative | Rows | Mixed dimensions | Other residual | Drilldown | Selected rows |",
            "| --- | ---: | --- | ---: | --- | --- |",
        ]
    )
    for row in summary_rows:
        selected_labels = str(row.get("selected_labels") or "").replace("|", "/")
        lines.append(
            "| "
            f"{row.get('alternative_result')} | "
            f"{row.get('row_count')} | "
            f"{row.get('selected_sequence_has_mixed_dimensions')} | "
            f"{_format_root_cause_brief_amount(row.get('other_residual'))} | "
            f"{row.get('drilldown_status')} | "
            f"{selected_labels} |"
        )
    lines.extend(
        [
            "",
            "## Recommended Structure",
            "",
            "1. Executive read: which alternatives are most useful and why.",
            "2. Deterministic facts: total delta, selected rows, residuals, and mixed-dimension flags.",
            "3. Interpretation: what the useful alternatives suggest, with residual logic explained.",
            "4. Drilldown recommendations: which generated rows deserve follow-up.",
            "5. Caveats: labels, currency assumptions, missing hierarchy meaning, and alternatives that are noisy or misleading.",
            "",
        ]
    )
    return "\n".join(lines)


def _legacy_chart_not_written_audit(
    exc: BaseException,
    *,
    artifact_name: str,
) -> dict[str, Any]:
    """Describe a non-blocking legacy chart render failure for audit output."""

    return {
        "status": "not_written_legacy_error",
        "artifact": artifact_name,
        "error": str(exc),
        "exception_type": exc.__class__.__name__,
    }


def _write_root_cause_sweep_outputs(
    bridge_result: Any,
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Write root-cause alternative sweep data and optional PNG artifacts."""

    if not bridge_result.sweep_runs:
        return [], {}
    paths: list[str] = []
    chart_audits: dict[str, Any] = {}
    alternatives: list[dict[str, Any]] = []
    for alternative, alternative_run in sorted(bridge_result.sweep_runs.items()):
        sequence = alternative_run.sequence
        bridge_path: Path | None = None
        chart_path: Path | None = None
        if not sequence.frame.is_empty():
            bridge_path = output_dir / f"root_cause_bridge_alt_{alternative}.csv"
            sequence.frame.write_csv(bridge_path)
            paths.append(str(bridge_path))
            chart_artifact = f"root_cause_bridge_alt_{alternative}.png"
            if render:
                try:
                    chart_export = write_root_cause_bridge_png(
                        sequence.frame,
                        result,
                        recipe,
                        output_dir,
                        artifact_name=chart_artifact,
                        legacy_frame=sequence.legacy_frame,
                        legacy_param=sequence.param,
                        legacy_chart=bridge_result.chart,
                        legacy_index_cols=bridge_result.bridge_dimensions,
                    )
                    paths.extend(chart_export.paths)
                    chart_audits[str(alternative)] = chart_export.audit
                    chart_path = output_dir / chart_artifact
                except LEGACY_RENDER_ERRORS as exc:
                    chart_audits[str(alternative)] = _legacy_chart_not_written_audit(
                        exc,
                        artifact_name=chart_artifact,
                    )
            else:
                chart_audits[str(alternative)] = _data_written_chart_audit(
                    chart_type=f"root_cause_bridge_alt_{alternative}",
                    artifact_name=chart_artifact,
                    source_functions=[
                        "legacy_adapter.run_legacy_variable_dimension_bridge"
                    ],
                )
        if (
            alternative_run.audit.get("drilldown_requested_rows")
            and not sequence.details_frame.is_empty()
        ):
            details_path = (
                output_dir / f"root_cause_bridge_alt_{alternative}_details.csv"
            )
            sequence.details_frame.write_csv(details_path)
            paths.append(str(details_path))
        if (
            alternative_run.audit.get("drilldown_requested_rows")
            and not sequence.snapshot_frame.is_empty()
        ):
            snapshot_path = (
                output_dir / f"root_cause_bridge_alt_{alternative}_snapshot.csv"
            )
            sequence.snapshot_frame.write_csv(snapshot_path)
            paths.append(str(snapshot_path))
        drilldown_chart_audits: dict[str, Any] = {}
        for row, drilldown_run in sorted(alternative_run.drilldown_runs.items()):
            if drilldown_run.frame.is_empty():
                continue
            drilldown_path = (
                output_dir
                / f"root_cause_bridge_alt_{alternative}_drilldown_row_{row}.csv"
            )
            drilldown_run.frame.write_csv(drilldown_path)
            paths.append(str(drilldown_path))
            parent_result = sequence.frame.slice(row - 1, 1)
            if parent_result.is_empty():
                continue
            drilldown_artifact = (
                f"root_cause_bridge_alt_{alternative}_drilldown_row_{row}.png"
            )
            if render:
                try:
                    drilldown_chart = write_root_cause_bridge_png(
                        drilldown_run.frame,
                        parent_result,
                        recipe,
                        output_dir,
                        artifact_name=drilldown_artifact,
                        legacy_frame=drilldown_run.legacy_frame,
                        legacy_param=drilldown_run.param,
                        legacy_chart=bridge_result.chart,
                        legacy_index_cols=bridge_result.bridge_dimensions,
                    )
                    paths.extend(drilldown_chart.paths)
                    drilldown_chart_audits[str(row)] = drilldown_chart.audit
                except LEGACY_RENDER_ERRORS as exc:
                    drilldown_chart_audits[str(row)] = _legacy_chart_not_written_audit(
                        exc,
                        artifact_name=drilldown_artifact,
                    )
            else:
                drilldown_chart_audits[str(row)] = _data_written_chart_audit(
                    chart_type=(
                        f"root_cause_bridge_alt_{alternative}_drilldown_row_{row}"
                    ),
                    artifact_name=drilldown_artifact,
                    source_functions=[
                        "legacy_adapter.run_legacy_variable_dimension_bridge"
                    ],
                )
        if drilldown_chart_audits:
            chart_audits[f"{alternative}_drilldowns"] = drilldown_chart_audits
        alternatives.append(
            _root_cause_sequence_payload(
                alternative_result=alternative,
                frame=sequence.frame,
                audit=alternative_run.audit,
                result=result,
                bridge_path=bridge_path,
                chart_path=chart_path,
            )
        )
    summary_rows = [
        {
            "alternative_result": alternative["alternative_result"],
            "row_count": alternative["row_count"],
            "selected_labels": " | ".join(
                row["label"] for row in alternative["selected_rows"]
            ),
            "selected_amounts": " | ".join(
                f"{row['variance_amount']:.6f}" for row in alternative["selected_rows"]
            ),
            "selected_sequence_bridge_dimensions": " | ".join(
                str(value)
                for value in alternative["selected_sequence_bridge_dimensions"]
            ),
            "selected_sequence_has_mixed_dimensions": alternative[
                "selected_sequence_has_mixed_dimensions"
            ],
            "other_residual": alternative["other_residual"],
            "drilldown_status": alternative["drilldown_status"],
            "automatic_drilldown_rows": " | ".join(
                str(value) for value in alternative["automatic_drilldown_rows"]
            ),
            "bridge_path": alternative["bridge_path"],
            "chart_path": alternative["chart_path"],
        }
        for alternative in alternatives
    ]
    if summary_rows:
        summary_path = output_dir / "root_cause_sweep_summary.csv"
        pl.DataFrame(summary_rows).write_csv(summary_path)
        paths.append(str(summary_path))
    context_payload = {
        "analysis_type": "root_cause_alternative_sweep",
        "codex_interpretation_contract": _root_cause_sweep_interpretation_contract(),
        "interpretation_rule": (
            "Each selected row is residual after all prior selected rows have "
            "been removed; mixed dimensions are valid but require this reading."
        ),
        "alternatives": alternatives,
    }
    client_report_paths, client_report_audit = write_root_cause_client_report(
        summary_rows=summary_rows,
        recipe=recipe,
        output_dir=output_dir,
    )
    paths.extend(client_report_paths)
    context_payload["client_report"] = client_report_audit
    chart_audits["client_report"] = client_report_audit
    context_path = output_dir / "root_cause_sweep_model_context.json"
    write_json(context_path, context_payload)
    paths.append(str(context_path))
    summary_json_path = output_dir / "root_cause_sweep_summary.json"
    write_json(summary_json_path, {"alternatives": summary_rows})
    paths.append(str(summary_json_path))
    brief_path = output_dir / "root_cause_sweep_interpretation_brief.md"
    brief_path.write_text(
        _root_cause_sweep_interpretation_brief(
            context_payload=context_payload,
            summary_rows=summary_rows,
        ),
        encoding="utf-8",
    )
    paths.append(str(brief_path))
    return paths, chart_audits


def write_root_cause_bridge(
    df: pl.DataFrame,
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None]:
    """Write root-cause data and optionally render bridge PNG artifacts."""

    if not bool(recipe["options"].get("root_cause_bridge")):
        return [], None, None
    try:
        bridge_result = run_legacy_variable_dimension_bridge(df, recipe)
    except LEGACY_RENDER_ERRORS as exc:
        LOGGER.warning("Root-cause bridge was not written: %s", exc)
        return (
            [],
            {
                "enabled": True,
                "status": "not_written_legacy_error",
                "reason": str(exc),
                "exception_type": exc.__class__.__name__,
            },
            None,
        )
    paths: list[str] = []
    drilldown_requested = bool(
        bridge_result.audit.get("drilldown_requested_rows")
        or bridge_result.audit.get("moved_rows_requested")
    )
    if not bridge_result.candidate_frame.is_empty():
        candidate_path = output_dir / "root_cause_bridge_candidates.csv"
        bridge_result.candidate_frame.write_csv(candidate_path)
        paths.append(str(candidate_path))
    if drilldown_requested and not bridge_result.details_frame.is_empty():
        details_path = output_dir / "root_cause_bridge_details.csv"
        bridge_result.details_frame.write_csv(details_path)
        paths.append(str(details_path))
    if drilldown_requested and not bridge_result.snapshot_frame.is_empty():
        snapshot_path = output_dir / "root_cause_bridge_snapshot.csv"
        bridge_result.snapshot_frame.write_csv(snapshot_path)
        paths.append(str(snapshot_path))
    if bridge_result.frame.is_empty():
        return paths, bridge_result.audit, None
    bridge_path = output_dir / "root_cause_total_bridge.csv"
    bridge_result.frame.write_csv(bridge_path)
    paths.append(str(bridge_path))
    chart_paths: list[str] = []
    chart_path: Path | None = None
    if render:
        try:
            chart_export = write_root_cause_bridge_png(
                bridge_result.frame,
                result,
                recipe,
                output_dir,
                artifact_name="root_cause_total_bridge.png",
                variance_mode="total_variance",
                legacy_frame=bridge_result.legacy_frame,
                legacy_param=bridge_result.param,
                legacy_chart=bridge_result.chart,
                legacy_index_cols=bridge_result.bridge_dimensions,
            )
            chart_paths = chart_export.paths
            chart_audit = chart_export.audit
            chart_path_value = chart_audit.get("path")
            chart_path = Path(str(chart_path_value)) if chart_path_value else None
        except LEGACY_RENDER_ERRORS as exc:
            LOGGER.warning("Root-cause bridge chart was not written: %s", exc)
            chart_audit = _legacy_chart_not_written_audit(
                exc,
                artifact_name="root_cause_total_bridge.png",
            )
    else:
        chart_audit = _data_written_chart_audit(
            chart_type=VARIANCE_CHART_ROOT_CAUSE,
            artifact_name="root_cause_total_bridge.png",
            source_functions=["legacy_adapter.run_legacy_variable_dimension_bridge"],
        )
        bridge_result.audit["status"] = "data_written"
        bridge_result.audit["rendered"] = False
    drilldown_chart_audits: dict[str, Any] = {}
    for row, drilldown_run in sorted(bridge_result.drilldown_runs.items()):
        if drilldown_run.frame.is_empty():
            continue
        drilldown_path = output_dir / f"root_cause_total_bridge_drilldown_row_{row}.csv"
        drilldown_run.frame.write_csv(drilldown_path)
        paths.append(str(drilldown_path))
        parent_result = bridge_result.frame.slice(row - 1, 1)
        if parent_result.is_empty():
            continue
        drilldown_artifact = f"root_cause_total_bridge_drilldown_row_{row}.png"
        if render:
            try:
                drilldown_chart = write_root_cause_bridge_png(
                    drilldown_run.frame,
                    parent_result,
                    recipe,
                    output_dir,
                    artifact_name=drilldown_artifact,
                    variance_mode="total_variance",
                    legacy_frame=drilldown_run.legacy_frame,
                    legacy_param=drilldown_run.param,
                    legacy_chart=bridge_result.chart,
                    legacy_index_cols=bridge_result.bridge_dimensions,
                )
            except LEGACY_RENDER_ERRORS as exc:
                drilldown_chart_audits[str(row)] = _legacy_chart_not_written_audit(
                    exc,
                    artifact_name=drilldown_artifact,
                )
                continue
            paths.extend(drilldown_chart.paths)
            drilldown_chart_audits[str(row)] = drilldown_chart.audit
        else:
            drilldown_chart_audits[str(row)] = _data_written_chart_audit(
                chart_type=f"root_cause_total_bridge_drilldown_row_{row}",
                artifact_name=drilldown_artifact,
                source_functions=[
                    "legacy_adapter.run_legacy_variable_dimension_bridge"
                ],
            )
    if drilldown_chart_audits:
        bridge_result.audit["drilldown_chart_audits"] = drilldown_chart_audits
    if (
        bridge_result.moved_run is not None
        and not bridge_result.moved_run.frame.is_empty()
    ):
        moved_path = output_dir / "root_cause_total_bridge_moved_rows.csv"
        bridge_result.moved_run.frame.write_csv(moved_path)
        paths.append(str(moved_path))
        if render:
            try:
                moved_chart = write_root_cause_bridge_png(
                    bridge_result.moved_run.frame,
                    result,
                    recipe,
                    output_dir,
                    artifact_name="root_cause_total_bridge_moved_rows.png",
                    variance_mode="total_variance",
                    legacy_frame=bridge_result.moved_run.legacy_frame,
                    legacy_param=bridge_result.moved_run.param,
                    legacy_chart=bridge_result.chart,
                    legacy_index_cols=bridge_result.bridge_dimensions,
                )
                paths.extend(moved_chart.paths)
                bridge_result.audit["moved_rows_chart_audit"] = moved_chart.audit
            except LEGACY_RENDER_ERRORS as exc:
                bridge_result.audit["moved_rows_chart_audit"] = (
                    _legacy_chart_not_written_audit(
                        exc,
                        artifact_name="root_cause_total_bridge_moved_rows.png",
                    )
                )
        else:
            bridge_result.audit["moved_rows_chart_audit"] = _data_written_chart_audit(
                chart_type="root_cause_total_bridge_moved_rows",
                artifact_name="root_cause_total_bridge_moved_rows.png",
                source_functions=[
                    "legacy_adapter.run_legacy_variable_dimension_bridge"
                ],
            )
    sweep_paths, sweep_chart_audits = _write_root_cause_sweep_outputs(
        bridge_result,
        result,
        recipe,
        output_dir,
        render=render,
    )
    paths.extend(sweep_paths)
    if sweep_chart_audits:
        bridge_result.audit["alternative_sweep_chart_audits"] = sweep_chart_audits
    context_path = _write_root_cause_bridge_context(
        frame=bridge_result.frame,
        result=result,
        recipe=recipe,
        audit=bridge_result.audit,
        output_dir=output_dir,
        bridge_path=bridge_path,
        chart_path=chart_path,
        context_name="root_cause_total_bridge_context.json",
        analysis_type="root_cause_total_bridge",
        capability_id="variance.root_cause_total_bridge",
        chart_type="root_cause_total_bridge",
    )
    paths.append(str(context_path))
    if bool(recipe.get("options", {}).get("root_cause_component_bridge")):
        try:
            component_result = run_legacy_variable_dimension_component_bridge(
                df,
                recipe,
            )
        except LEGACY_RENDER_ERRORS as exc:
            bridge_result.audit["component_bridge_audit"] = {
                "enabled": True,
                "status": "not_written_legacy_error",
                "reason": str(exc),
                "exception_type": exc.__class__.__name__,
                "root_cause_variance_mode": "component_variance",
            }
        else:
            bridge_result.audit["component_bridge_audit"] = component_result.audit
            if not component_result.candidate_frame.is_empty():
                component_candidate_path = (
                    output_dir / "root_cause_component_bridge_candidates.csv"
                )
                component_result.candidate_frame.write_csv(component_candidate_path)
                paths.append(str(component_candidate_path))
            if not component_result.frame.is_empty():
                component_path = output_dir / "root_cause_component_bridge.csv"
                component_result.frame.write_csv(component_path)
                paths.append(str(component_path))
                component_chart_path: Path | None = None
                try:
                    component_chart = write_root_cause_bridge_png(
                        component_result.frame,
                        result,
                        recipe,
                        output_dir,
                        artifact_name="root_cause_component_bridge.png",
                        variance_mode="component_variance",
                        legacy_frame=component_result.legacy_frame,
                        legacy_param=component_result.param,
                        legacy_chart=component_result.chart,
                        legacy_index_cols=component_result.bridge_dimensions,
                    )
                    paths.extend(component_chart.paths)
                    bridge_result.audit["component_bridge_chart_audit"] = (
                        component_chart.audit
                    )
                    chart_path_value = component_chart.audit.get("path")
                    component_chart_path = (
                        Path(str(chart_path_value)) if chart_path_value else None
                    )
                except LEGACY_RENDER_ERRORS as exc:
                    bridge_result.audit["component_bridge_chart_audit"] = (
                        _legacy_chart_not_written_audit(
                            exc,
                            artifact_name="root_cause_component_bridge.png",
                        )
                    )
                component_context = _write_root_cause_bridge_context(
                    frame=component_result.frame,
                    result=result,
                    recipe=recipe,
                    audit=component_result.audit,
                    output_dir=output_dir,
                    bridge_path=component_path,
                    chart_path=component_chart_path,
                    context_name="root_cause_component_bridge_context.json",
                    analysis_type="root_cause_component_bridge",
                    capability_id="variance.root_cause_component_bridge",
                    chart_type="root_cause_component_bridge",
                )
                paths.append(str(component_context))
    return (
        [*paths, *chart_paths],
        bridge_result.audit,
        chart_audit,
    )


def run_variance_analysis(
    input_path: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    root_cause_bridge: bool | None = None,
    root_cause_bridge_alternative_result: int | None = None,
    root_cause_bridge_drilldown_rows: list[int] | None = None,
    root_cause_bridge_drilldown_all: bool | None = None,
    root_cause_bridge_move_rows: dict[int | str, list[int]] | None = None,
    root_cause_bridge_alternative_sweep: bool | None = None,
    root_cause_bridge_alternative_sweep_start: int | None = None,
    root_cause_bridge_alternative_sweep_end: int | None = None,
    root_cause_bridge_auto_drilldown: str | None = None,
    root_cause_bridge_auto_drilldown_min_share: float | None = None,
    root_cause_component_bridge: bool | None = None,
    root_cause_component_bridge_alternative_result: int | None = None,
    waterfall_chart: bool | None = None,
    waterfall_small_multiples: bool | None = None,
    waterfall_small_multiples_dimension: str | None = None,
    total_by_dimension_bridge: bool | None = None,
    total_by_dimension_bridge_dimension: str | None = None,
    total_by_dimension_bridge_top_n: int | None = None,
    exploded_variance_bridge: bool | None = None,
    exploded_variance_bridge_parent_dimension: str | None = None,
    exploded_variance_bridge_child_dimension: str | None = None,
    exploded_variance_bridge_parent_top_n: int | None = None,
    exploded_variance_bridge_child_top_n: int | None = None,
    exploded_variance_bridge_max_drilldowns: int | None = None,
    currency: str | None = None,
    language: str = "en",
    artifact_mode: str = ARTIFACT_MODE_DATA_AND_RENDER,
) -> VarianceRunResult:
    """Run deterministic variance analysis and write output artifacts."""

    artifact_mode = _normalize_artifact_mode(artifact_mode)
    try:
        df = read_table(input_path)
        recipe = build_recipe(input_path, df, language=language)
        existing_recipe = None
        if recipe_path:
            existing_recipe = load_json(recipe_path)
            recipe = build_recipe(
                input_path,
                df,
                language=language,
                existing_recipe=existing_recipe,
            )
        recipe = preserve_recipe_filters(recipe, existing_recipe)
        recipe = preserve_recipe_cohorts(recipe, existing_recipe)
        if currency is not None:
            recipe.setdefault("options", {})["currency"] = currency
        recipe = validate_recipe(df, recipe)
        if root_cause_bridge is not None:
            recipe["options"]["root_cause_bridge"] = root_cause_bridge
        if root_cause_bridge_alternative_result is not None:
            recipe["options"][
                "root_cause_bridge_alternative_result"
            ] = root_cause_bridge_alternative_result
        if root_cause_bridge_drilldown_rows is not None:
            recipe["options"][
                "root_cause_bridge_drilldown_rows"
            ] = root_cause_bridge_drilldown_rows
        if root_cause_bridge_drilldown_all is not None:
            recipe["options"][
                "root_cause_bridge_drilldown_all"
            ] = root_cause_bridge_drilldown_all
        if root_cause_bridge_move_rows is not None:
            recipe["options"][
                "root_cause_bridge_move_rows"
            ] = root_cause_bridge_move_rows
        if root_cause_bridge_alternative_sweep is not None:
            recipe["options"][
                "root_cause_bridge_alternative_sweep"
            ] = root_cause_bridge_alternative_sweep
            if root_cause_bridge_alternative_sweep:
                recipe["options"]["root_cause_bridge"] = True
        if root_cause_bridge_alternative_sweep_start is not None:
            recipe["options"][
                "root_cause_bridge_alternative_sweep_start"
            ] = root_cause_bridge_alternative_sweep_start
        if root_cause_bridge_alternative_sweep_end is not None:
            recipe["options"][
                "root_cause_bridge_alternative_sweep_end"
            ] = root_cause_bridge_alternative_sweep_end
        if root_cause_bridge_auto_drilldown is not None:
            recipe["options"][
                "root_cause_bridge_auto_drilldown"
            ] = root_cause_bridge_auto_drilldown
        if root_cause_bridge_auto_drilldown_min_share is not None:
            recipe["options"][
                "root_cause_bridge_auto_drilldown_min_share"
            ] = root_cause_bridge_auto_drilldown_min_share
        if root_cause_component_bridge is not None:
            recipe["options"][
                "root_cause_component_bridge"
            ] = root_cause_component_bridge
            if root_cause_component_bridge:
                recipe["options"]["root_cause_bridge"] = True
        if root_cause_component_bridge_alternative_result is not None:
            recipe["options"][
                "root_cause_component_bridge_alternative_result"
            ] = root_cause_component_bridge_alternative_result
        if waterfall_chart is not None:
            recipe["options"]["waterfall_chart"] = waterfall_chart
        if waterfall_small_multiples is not None:
            recipe["options"]["waterfall_small_multiples"] = waterfall_small_multiples
        if waterfall_small_multiples_dimension:
            recipe["options"][
                "waterfall_small_multiples_dimension"
            ] = waterfall_small_multiples_dimension
        if total_by_dimension_bridge is not None:
            recipe["options"]["total_by_dimension_bridge"] = total_by_dimension_bridge
        if total_by_dimension_bridge_dimension:
            recipe["options"][
                "total_by_dimension_bridge_dimension"
            ] = total_by_dimension_bridge_dimension
        if total_by_dimension_bridge_top_n is not None:
            recipe["options"][
                "total_by_dimension_bridge_top_n"
            ] = total_by_dimension_bridge_top_n
        if exploded_variance_bridge is not None:
            recipe["options"]["exploded_variance_bridge"] = exploded_variance_bridge
        if exploded_variance_bridge_parent_dimension:
            recipe["options"][
                "exploded_variance_bridge_parent_dimension"
            ] = exploded_variance_bridge_parent_dimension
        if exploded_variance_bridge_child_dimension:
            recipe["options"][
                "exploded_variance_bridge_child_dimension"
            ] = exploded_variance_bridge_child_dimension
        if exploded_variance_bridge_parent_top_n is not None:
            recipe["options"][
                "exploded_variance_bridge_parent_top_n"
            ] = exploded_variance_bridge_parent_top_n
        if exploded_variance_bridge_child_top_n is not None:
            recipe["options"][
                "exploded_variance_bridge_child_top_n"
            ] = exploded_variance_bridge_child_top_n
        if exploded_variance_bridge_max_drilldowns is not None:
            recipe["options"][
                "exploded_variance_bridge_max_drilldowns"
            ] = exploded_variance_bridge_max_drilldowns
        df, recipe = prepare_period_comparison_buckets(df, recipe)
        df, filter_audit = apply_recipe_filters(df, recipe)
        recipe.setdefault("options", {})["recipe_filter_audit"] = filter_audit
        df, cohort_audit = apply_recipe_cohorts(
            df,
            recipe,
            period_column=str(recipe["mappings"]["period_column"]),
            value_column=str(recipe["mappings"]["amount_column"]),
            current_period=str(recipe["mappings"]["comparison_period"]),
            previous_period=str(recipe["mappings"]["baseline_period"]),
        )
        recipe = validate_recipe(df, recipe)
        warn_if_output_dir_has_existing_files(output_dir, "Variance")
        output_dir.mkdir(parents=True, exist_ok=True)
        run_intake = write_run_intake(
            output_dir,
            input_path,
            recipe_path=recipe_path,
            recipe=recipe,
            source_row_count=df.height,
        )

        legacy_result = run_legacy_variance(
            df, recipe, list(recipe["mappings"].get("dimensions") or [])
        )
        result = legacy_result.frame
        if bool(recipe["options"].get("waterfall_small_multiples")):
            small_multiples_selection = select_waterfall_small_multiples_dimension(
                result,
                recipe,
            )
        else:
            small_multiples_selection = {
                "status": "disabled",
                "reason": "waterfall_small_multiples is false",
                "dimension": None,
            }
        recipe["options"][
            "waterfall_small_multiples_dimension_selection"
        ] = small_multiples_selection
        selected_small_multiples_dimension = small_multiples_selection.get("dimension")
        recipe["options"]["waterfall_small_multiples"] = bool(
            selected_small_multiples_dimension
        )
        recipe["options"][
            "waterfall_small_multiples_dimension"
        ] = selected_small_multiples_dimension
        if bool(recipe["options"].get("total_by_dimension_bridge")):
            total_bridge_selection = select_total_by_dimension_bridge_dimension(
                result,
                recipe,
            )
        else:
            total_bridge_selection = {
                "status": "disabled",
                "reason": "total_by_dimension_bridge is false",
                "dimension": None,
            }
        recipe["options"][
            "total_by_dimension_bridge_dimension_selection"
        ] = total_bridge_selection
        selected_total_bridge_dimension = total_bridge_selection.get("dimension")
        recipe["options"]["total_by_dimension_bridge"] = bool(
            selected_total_bridge_dimension
        )
        recipe["options"][
            "total_by_dimension_bridge_dimension"
        ] = selected_total_bridge_dimension
        if bool(recipe["options"].get("exploded_variance_bridge")):
            exploded_bridge_selection = select_exploded_variance_bridge_dimensions(
                result,
                recipe,
                fallback_parent_dimension=(
                    str(selected_total_bridge_dimension)
                    if selected_total_bridge_dimension
                    else None
                ),
            )
        else:
            exploded_bridge_selection = {
                "status": "disabled",
                "reason": "exploded_variance_bridge is false",
                "parent_dimension": None,
                "child_dimension": None,
            }
        recipe["options"][
            "exploded_variance_bridge_dimension_selection"
        ] = exploded_bridge_selection
        selected_exploded_parent_dimension = exploded_bridge_selection.get(
            "parent_dimension"
        )
        selected_exploded_child_dimension = exploded_bridge_selection.get(
            "child_dimension"
        )
        recipe["options"]["exploded_variance_bridge"] = bool(
            selected_exploded_parent_dimension and selected_exploded_child_dimension
        )
        recipe["options"][
            "exploded_variance_bridge_parent_dimension"
        ] = selected_exploded_parent_dimension
        recipe["options"][
            "exploded_variance_bridge_child_dimension"
        ] = selected_exploded_child_dimension
        available_chart_types = []
        if bool(recipe["options"].get("waterfall_chart", True)):
            available_chart_types.append(VARIANCE_CHART_STANDARD_WATERFALL)
        if recipe.get("mappings", {}).get("units_column") and bool(
            recipe.get("options", {}).get("pvm_decomposition_ladder", True)
        ):
            available_chart_types.append(VARIANCE_CHART_PVM_LADDER)
        if bool(recipe["options"].get("waterfall_small_multiples")):
            available_chart_types.append(VARIANCE_CHART_SMALL_MULTIPLES)
        if selected_total_bridge_dimension:
            available_chart_types.append(VARIANCE_CHART_TOTAL_BY_DIMENSION)
        if selected_exploded_parent_dimension and selected_exploded_child_dimension:
            available_chart_types.append(VARIANCE_CHART_EXPLODED_BRIDGE)
        if bool(recipe["options"].get("root_cause_bridge", True)):
            available_chart_types.append(VARIANCE_CHART_ROOT_CAUSE)
        render_standard_waterfall = _variance_chart_selected(
            VARIANCE_CHART_STANDARD_WATERFALL,
            artifact_mode,
            available_chart_types,
        )
        render_small_multiples = _variance_chart_selected(
            VARIANCE_CHART_SMALL_MULTIPLES,
            artifact_mode,
            available_chart_types,
        )
        if artifact_mode == ARTIFACT_MODE_DATA_ONLY and _variance_data_chart_enabled(
            VARIANCE_CHART_STANDARD_WATERFALL,
            available_chart_types,
        ):
            waterfall_export = argparse.Namespace(
                paths=[],
                audit=_data_written_chart_audit(
                    chart_type=VARIANCE_CHART_STANDARD_WATERFALL,
                    artifact_name="waterfall.png",
                    source_functions=[
                        "modules.charting.draw_waterfall.draw_vertical_waterfall_chart"
                    ],
                ),
            )
            if _variance_data_chart_enabled(
                VARIANCE_CHART_SMALL_MULTIPLES,
                available_chart_types,
            ):
                waterfall_export.audit["small_multiples_status"] = "data_written"
                waterfall_export.audit["small_multiples_artifact"] = (
                    "waterfall_small_multiples.png"
                )
        elif artifact_mode == ARTIFACT_MODE_DATA_ONLY:
            waterfall_export = argparse.Namespace(
                paths=[],
                audit=_skipped_chart_audit(
                    VARIANCE_CHART_STANDARD_WATERFALL,
                    "not enabled in recipe",
                ),
            )
        elif render_standard_waterfall or render_small_multiples:
            waterfall_export = write_waterfall_png(
                result,
                recipe,
                output_dir,
                legacy_frame=legacy_result.legacy_frame,
                render_standard=render_standard_waterfall,
                render_small_multiples=render_small_multiples,
            )
        else:
            waterfall_export = argparse.Namespace(
                paths=[],
                audit=_skipped_chart_audit(
                    VARIANCE_CHART_STANDARD_WATERFALL,
                    "not enabled in recipe",
                ),
            )
        render_pvm_ladder = _variance_chart_selected(
            VARIANCE_CHART_PVM_LADDER,
            artifact_mode,
            available_chart_types,
        )
        if artifact_mode == ARTIFACT_MODE_DATA_ONLY and _variance_data_chart_enabled(
            VARIANCE_CHART_PVM_LADDER,
            available_chart_types,
        ):
            pvm_ladder_export = argparse.Namespace(
                paths=[],
                audit=_data_written_chart_audit(
                    chart_type=VARIANCE_CHART_PVM_LADDER,
                    artifact_name="pvm_decomposition_ladder.png",
                    source_functions=[
                        "modules.charting.draw_waterfall.draw_vertical_waterfall_chart"
                    ],
                ),
            )
        elif render_pvm_ladder:
            pvm_ladder_export = write_pvm_decomposition_ladder_png(
                result,
                recipe,
                output_dir,
                legacy_frame=legacy_result.legacy_frame,
            )
        else:
            pvm_ladder_export = argparse.Namespace(
                paths=[],
                audit=_skipped_chart_audit(
                    VARIANCE_CHART_PVM_LADDER,
                    "not enabled in recipe",
                ),
            )
        (
            pvm_ladder_chart_data_paths,
            pvm_ladder_chart_data_audit,
            pvm_ladder_summary,
        ) = write_pvm_decomposition_ladder_chart_data(result, recipe, output_dir)
        (
            small_multiples_chart_data_paths,
            small_multiples_chart_data_audit,
            small_multiples_summary,
        ) = write_waterfall_small_multiples_chart_data(result, recipe, output_dir)
        render_total_by_dimension = _variance_chart_selected(
            VARIANCE_CHART_TOTAL_BY_DIMENSION,
            artifact_mode,
            available_chart_types,
        )
        if selected_total_bridge_dimension and artifact_mode == ARTIFACT_MODE_DATA_ONLY:
            total_by_dimension_export = write_total_by_dimension_bridge_artifacts(
                result,
                recipe,
                output_dir,
                dimension=str(selected_total_bridge_dimension),
                top_n=int(recipe["options"]["total_by_dimension_bridge_top_n"]),
                render=False,
            )
        elif selected_total_bridge_dimension and render_total_by_dimension:
            total_by_dimension_export = write_total_by_dimension_bridge_artifacts(
                result,
                recipe,
                output_dir,
                dimension=str(selected_total_bridge_dimension),
                top_n=int(recipe["options"]["total_by_dimension_bridge_top_n"]),
            )
        else:
            total_by_dimension_export = argparse.Namespace(
                paths=[],
                audit={
                    "enabled": bool(recipe["options"].get("total_by_dimension_bridge")),
                    "status": total_bridge_selection["status"],
                    "dimension": None,
                    "selection": total_bridge_selection,
                },
                summary_markdown="",
            )
        render_exploded_bridge = _variance_chart_selected(
            VARIANCE_CHART_EXPLODED_BRIDGE,
            artifact_mode,
            available_chart_types,
        )
        if (
            selected_exploded_parent_dimension
            and selected_exploded_child_dimension
            and artifact_mode == ARTIFACT_MODE_DATA_ONLY
        ):
            exploded_bridge_export = write_exploded_variance_bridge_artifacts(
                result,
                recipe,
                output_dir,
                parent_dimension=str(selected_exploded_parent_dimension),
                child_dimension=str(selected_exploded_child_dimension),
                parent_top_n=int(
                    recipe["options"]["exploded_variance_bridge_parent_top_n"]
                ),
                child_top_n=int(
                    recipe["options"]["exploded_variance_bridge_child_top_n"]
                ),
                max_drilldowns=int(
                    recipe["options"]["exploded_variance_bridge_max_drilldowns"]
                ),
                render=False,
            )
        elif (
            selected_exploded_parent_dimension
            and selected_exploded_child_dimension
            and render_exploded_bridge
        ):
            exploded_bridge_export = write_exploded_variance_bridge_artifacts(
                result,
                recipe,
                output_dir,
                parent_dimension=str(selected_exploded_parent_dimension),
                child_dimension=str(selected_exploded_child_dimension),
                parent_top_n=int(
                    recipe["options"]["exploded_variance_bridge_parent_top_n"]
                ),
                child_top_n=int(
                    recipe["options"]["exploded_variance_bridge_child_top_n"]
                ),
                max_drilldowns=int(
                    recipe["options"]["exploded_variance_bridge_max_drilldowns"]
                ),
            )
        else:
            exploded_bridge_export = argparse.Namespace(
                paths=[],
                audit={
                    "enabled": bool(recipe["options"].get("exploded_variance_bridge")),
                    "status": exploded_bridge_selection["status"],
                    "parent_dimension": None,
                    "child_dimension": None,
                    "selection": exploded_bridge_selection,
                },
                summary_markdown="",
            )
        render_root_cause = _variance_chart_selected(
            VARIANCE_CHART_ROOT_CAUSE,
            artifact_mode,
            available_chart_types,
        )
        if artifact_mode == ARTIFACT_MODE_DATA_ONLY and _variance_data_chart_enabled(
            VARIANCE_CHART_ROOT_CAUSE,
            available_chart_types,
        ):
            bridge_paths, bridge_audit, bridge_chart_audit = write_root_cause_bridge(
                df,
                result,
                recipe,
                output_dir,
                render=False,
            )
        elif render_root_cause:
            bridge_paths, bridge_audit, bridge_chart_audit = write_root_cause_bridge(
                df,
                result,
                recipe,
                output_dir,
            )
        else:
            bridge_paths = []
            bridge_audit = None
            bridge_chart_audit = bridge_audit
        summary = build_summary_markdown(result, recipe)
        summary += pvm_ladder_summary
        summary += small_multiples_summary
        summary += total_by_dimension_export.summary_markdown
        summary += exploded_bridge_export.summary_markdown
        summary = append_bridge_dimension_summary(summary, bridge_audit)
        artifact_paths = [
            *bridge_paths,
            *waterfall_export.paths,
            *pvm_ladder_export.paths,
            *pvm_ladder_chart_data_paths,
            *small_multiples_chart_data_paths,
            *total_by_dimension_export.paths,
            *exploded_bridge_export.paths,
        ]
        audit = build_audit(input_path, recipe, result, artifact_paths)
        audit["legacy_runtime"] = legacy_result.audit
        audit["legacy_runtime"]["variable_dimension_bridge"] = bridge_audit
        audit["legacy_runtime"]["variable_dimension_bridge_chart"] = bridge_chart_audit
        audit["legacy_runtime"]["waterfall_chart"] = waterfall_export.audit
        audit["legacy_runtime"][
            "pvm_decomposition_ladder_chart"
        ] = pvm_ladder_export.audit
        audit["legacy_runtime"][
            "pvm_decomposition_ladder_chart_data"
        ] = pvm_ladder_chart_data_audit
        audit["legacy_runtime"][
            "waterfall_small_multiples_dimension_selection"
        ] = small_multiples_selection
        audit["legacy_runtime"][
            "waterfall_small_multiples_chart_data"
        ] = small_multiples_chart_data_audit
        audit["legacy_runtime"][
            "total_by_dimension_bridge_dimension_selection"
        ] = total_bridge_selection
        audit["legacy_runtime"][
            "total_by_dimension_bridge"
        ] = total_by_dimension_export.audit
        audit["legacy_runtime"][
            "exploded_variance_bridge_dimension_selection"
        ] = exploded_bridge_selection
        audit["legacy_runtime"][
            "exploded_variance_bridge"
        ] = exploded_bridge_export.audit
        if waterfall_export.audit.get("status") == "not_written":
            audit["outputs"]["waterfall.png"] = "not_written: " + str(
                waterfall_export.audit.get("error", "unknown")
            )
        if waterfall_export.audit.get("small_multiples_status") == "not_written":
            audit["outputs"]["waterfall_small_multiples.png"] = "not_written: " + str(
                waterfall_export.audit.get("small_multiples_error", "unknown")
            )
        if pvm_ladder_export.audit.get("status", "").startswith("not_written"):
            audit["outputs"]["pvm_decomposition_ladder.png"] = "not_written: " + str(
                pvm_ladder_export.audit.get(
                    "error", pvm_ladder_export.audit.get("reason", "unknown")
                )
            )
        audit["legacy_runtime"]["artifact_mode"] = artifact_mode
        chart_statuses = {
            VARIANCE_CHART_STANDARD_WATERFALL: waterfall_export.audit.get("status"),
            VARIANCE_CHART_PVM_LADDER: pvm_ladder_export.audit.get("status"),
            VARIANCE_CHART_SMALL_MULTIPLES: (
                waterfall_export.audit.get("small_multiples_status")
                or small_multiples_chart_data_audit.get("status")
            ),
            VARIANCE_CHART_TOTAL_BY_DIMENSION: (
                total_by_dimension_export.audit.get("status")
            ),
            VARIANCE_CHART_EXPLODED_BRIDGE: (
                exploded_bridge_export.audit.get("status")
            ),
            VARIANCE_CHART_ROOT_CAUSE: (
                bridge_audit.get("status") if bridge_audit else None
            ),
        }
        audit["checks"]["legacy_chart_attempt_count"] = sum(
            1
            for status in chart_statuses.values()
            if status not in {None, "skipped", "disabled"}
        )
        audit["checks"]["legacy_chart_written_count"] = sum(
            1 for status in chart_statuses.values() if status == "written"
        )
        audit["checks"]["legacy_chart_data_count"] = sum(
            1
            for status in chart_statuses.values()
            if status in {"written", "data_written"}
        )
        write_json(output_dir / "used_recipe.json", recipe)
        audit["outputs"]["used_recipe.json"] = "written"
        write_outputs(result, audit, summary, output_dir, artifact_paths=artifact_paths)
        prepared_manifest_path = write_prepared_data_manifest(
            output_dir=output_dir,
            plugin="variance-analysis",
            chart_family="variance_analysis",
            source_file=input_path,
            prepared_path=output_dir / "variance_results.csv",
            frame=result,
            recipe=recipe,
            stage="variance_result",
            preparation_audit={
                "status": "prepared",
                "recipe_filters": filter_audit,
                "recipe_cohorts": cohort_audit,
                "legacy_runtime": legacy_result.audit,
            },
        )
        audit["outputs"][
            _relative_artifact_path(prepared_manifest_path, output_dir)
        ] = "written"
        standard_context_path = output_dir / "standard_variance_context.json"
        write_json(
            standard_context_path,
            _standard_variance_context(result, recipe, output_dir),
        )
        audit["outputs"][
            _relative_artifact_path(standard_context_path, output_dir)
        ] = "written"
        write_json(output_dir / "variance_audit.json", audit)
        artifact_paths = [
            *artifact_paths,
            str(prepared_manifest_path),
            str(standard_context_path),
        ]
        review_session = write_review_session_artifacts(
            output_dir,
            input_path,
            run_id=run_intake.run_id,
            run_intake_path=run_intake.path,
            recipe_path=recipe_path,
            recipe=recipe,
            result_rows=result.to_dicts(),
            audit=audit,
        )
        audit["review_session"] = {
            "run_intake_path": review_session.run_intake_path.name,
            "review_payload_path": review_session.review_payload_path.name,
            "ui_decisions_path": review_session.ui_decisions_path.name,
            "final_artifacts_path": review_session.final_artifacts_path.name,
            "review_item_count": review_session.review_item_count,
        }
        for path in (
            review_session.run_intake_path,
            review_session.review_payload_path,
            review_session.ui_decisions_path,
            review_session.final_artifacts_path,
        ):
            audit["outputs"][_relative_artifact_path(path, output_dir)] = "written"
        artifact_paths = [
            *artifact_paths,
            str(review_session.run_intake_path),
            str(review_session.review_payload_path),
            str(review_session.ui_decisions_path),
            str(review_session.final_artifacts_path),
        ]
        write_json(output_dir / "variance_audit.json", audit)
        return VarianceRunResult(
            frame=result,
            audit=audit,
            summary_markdown=summary,
            artifact_paths=artifact_paths,
        )
    finally:
        cleanup_legacy_imports()
