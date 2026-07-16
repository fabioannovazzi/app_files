"""Deterministic Venn and UpSet overlap analysis for chart-family runs."""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
import tempfile
import warnings
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl

try:
    from .review_session import write_review_session_artifacts, write_run_intake
except ImportError:  # pragma: no cover - supports direct script imports
    import importlib.util

    _review_session_path = Path(__file__).resolve().parent / "review_session.py"
    _review_session_spec = importlib.util.spec_from_file_location(
        "mparanza_set_overlap_review_session",
        _review_session_path,
    )
    assert _review_session_spec and _review_session_spec.loader
    _review_session = importlib.util.module_from_spec(_review_session_spec)
    sys.modules[_review_session_spec.name] = _review_session
    _review_session_spec.loader.exec_module(_review_session)
    write_review_session_artifacts = _review_session.write_review_session_artifacts
    write_run_intake = _review_session.write_run_intake

__all__ = [
    "InspectionResult",
    "SetOverlapRunResult",
    "add_common_args",
    "build_overlap_tables",
    "build_recipe",
    "configure_logging",
    "inspect_set_overlap_inputs",
    "read_json",
    "read_table",
    "run_set_overlap",
    "validate_recipe",
    "write_json",
]

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "set-overlap-analysis"
CANONICAL_ITEM = "item"
CANONICAL_SET = "set"
CANONICAL_PERIOD = "period"
CANONICAL_FACET = "facet"
ALL_PERIOD_LABEL = "All"
SUPPORTED_CHARTS = {"upset", "venn", "upset_small_multiples"}
ARTIFACT_MODE_DATA_ONLY = "data_only"
ARTIFACT_MODE_DATA_AND_RENDER = "data_and_render"
ARTIFACT_MODES = {
    ARTIFACT_MODE_DATA_ONLY,
    ARTIFACT_MODE_DATA_AND_RENDER,
}
CSV_EXTENSIONS = {".csv", ".txt", ".tsv", ".psv"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_VENDOR_ROOT = REPO_ROOT / "plugins" / "_shared" / "vendor"
VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor"


def _legacy_import_parent() -> Path:
    """Return shared modules in the repo or this component's packaged vendor."""

    if (SHARED_VENDOR_ROOT / "modules" / "__init__.py").exists():
        return SHARED_VENDOR_ROOT
    return VENDOR_ROOT


def _activate_legacy_import_parent() -> Path:
    """Prioritize the selected vendor and evict incompatible ``modules`` imports."""

    legacy_parent = _legacy_import_parent()
    legacy_text = str(legacy_parent)
    while legacy_text in sys.path:
        sys.path.remove(legacy_text)
    sys.path.insert(0, legacy_text)
    module_root = (legacy_parent / "modules").resolve()
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            if not module_file or not Path(module_file).resolve().is_relative_to(
                module_root
            ):
                del sys.modules[name]
    return legacy_parent


_activate_legacy_import_parent()
from modules.chart_harness import (  # noqa: E402
    reporting_subject_label_from_recipe,
    reporting_title_html,
)
from modules.charting.static_export import (  # noqa: E402
    normalize_plotly_figure_for_static_export,
)

UPSET_TITLE_TOP_MARGIN = 96
UPSET_TITLE_BOTTOM_MARGIN = 45
SET_OVERLAP_CHART_FONT_SIZE = 12
UPSET_TITLE_FONT_SIZE = SET_OVERLAP_CHART_FONT_SIZE
UPSET_TITLE_COLOR = "#1F2328"
UPSET_TITLE_Y = 0.94
DEFAULT_SMALL_MULTIPLES_MAX_PANELS = 6
OTHER_RANK_LABEL_PREFIX = "Other rank >"

ITEM_NAME_HINTS = (
    "sku",
    "product",
    "item",
    "article",
    "ean",
    "upc",
    "gtin",
    "id",
    "customer",
    "client",
    "store",
    "name",
)
SET_NAME_HINTS = (
    "set",
    "group",
    "company",
    "manufacturer",
    "retailer",
    "channel",
    "region",
    "segment",
    "brand",
    "category",
    "scenario",
    "market",
    "period",
)
PERIOD_NAME_HINTS = ("period", "scenario", "month", "week", "date", "year")
VENN_EXPORT_WIDTH = 1400
VENN_EXPORT_HEIGHT = 900
VENN_EXPORT_DPI = 100
VENN_FALLBACK_COLORS = ("#343434", "#999A9A", "#818284")
PALETTE_OPTION_KEYS = ("colorpalette", "color_palette", "palette", "chart_palette")


@dataclass(frozen=True)
class InspectionResult:
    """Inspection payload and suggested recipe."""

    payload: dict[str, Any]
    recipe: dict[str, Any]
    output_dir: Path


@dataclass(frozen=True)
class SetOverlapRunResult:
    """Set-overlap run result."""

    canonical_frame: pl.DataFrame
    context: dict[str, Any]
    audit: dict[str, Any]
    artifact_paths: list[str]
    review_session: dict[str, Any] | None = None


def configure_logging(verbose: bool = False) -> None:
    """Configure command-line logging."""

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common plugin CLI arguments."""

    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--language", default="en")
    parser.add_argument(
        "--artifact-mode",
        choices=sorted(ARTIFACT_MODES),
        default=ARTIFACT_MODE_DATA_AND_RENDER,
        help=(
            "Write chart data/context only or keep the legacy data-and-render behavior."
        ),
    )
    parser.add_argument("--verbose", action="store_true")


def utc_now() -> str:
    """Return an ISO timestamp for audit outputs."""

    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path | None) -> dict[str, Any] | None:
    """Read a JSON object from ``path`` when present."""

    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a deterministic JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, frame: pl.DataFrame) -> None:
    """Write a CSV, flattening list columns for CSV compatibility."""

    path.parent.mkdir(parents=True, exist_ok=True)
    expressions: list[pl.Expr] = []
    for name, dtype in frame.schema.items():
        if str(dtype).startswith("List"):
            expressions.append(pl.col(name).list.join(" | ").alias(name))
        else:
            expressions.append(pl.col(name))
    frame.select(expressions).write_csv(path)


def _collect_csv_scan(path: Path, *, separator: str) -> pl.DataFrame:
    """Read delimited input through a lazy scan and collect once."""

    lf = pl.scan_csv(path, separator=separator, infer_schema_length=10000)
    try:
        return lf.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return lf.collect()


def read_table(path: Path) -> pl.DataFrame:
    """Read CSV, TSV, PSV, TXT, XLSX, XLSM or XLS into Polars."""

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


def _schema(frame: pl.DataFrame) -> dict[str, pl.DataType]:
    return dict(frame.schema)


def _column_names(frame: pl.DataFrame) -> list[str]:
    return list(frame.schema.keys())


def _is_numeric_dtype(dtype: pl.DataType) -> bool:
    checker = getattr(dtype, "is_numeric", None)
    if callable(checker):
        return bool(checker())
    return dtype in {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    }


def _safe_unique_count(frame: pl.DataFrame, column: str) -> int:
    try:
        value = frame.select(pl.col(column).n_unique().alias("n")).item()
    except (pl.exceptions.PolarsError, TypeError, ValueError):
        return 0
    return int(value or 0)


def _column_profile(frame: pl.DataFrame) -> list[dict[str, Any]]:
    schema = _schema(frame)
    row_count = frame.height
    profiles: list[dict[str, Any]] = []
    for column in _column_names(frame):
        unique_count = _safe_unique_count(frame, column)
        profiles.append(
            {
                "column": column,
                "dtype": str(schema[column]),
                "unique_count": unique_count,
                "unique_share": unique_count / row_count if row_count else 0.0,
                "is_numeric": _is_numeric_dtype(schema[column]),
            }
        )
    return profiles


def _normalized_name(column: str) -> str:
    return column.lower().replace("_", " ").replace("-", " ")


def _has_hint(column: str, hints: tuple[str, ...]) -> bool:
    normalized = _normalized_name(column)
    return any(hint in normalized for hint in hints)


def _infer_period_column(profiles: list[dict[str, Any]]) -> str | None:
    candidates = [
        item
        for item in profiles
        if _has_hint(str(item["column"]), PERIOD_NAME_HINTS)
        and int(item["unique_count"]) >= 2
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            0 if _normalized_name(str(item["column"])) in {"period", "scenario"} else 1,
            int(item["unique_count"]),
        )
    )
    return str(candidates[0]["column"])


def _infer_item_column(profiles: list[dict[str, Any]]) -> str | None:
    candidates: list[tuple[float, str]] = []
    for item in profiles:
        column = str(item["column"])
        unique_count = int(item["unique_count"])
        if unique_count < 2:
            continue
        score = float(unique_count)
        if _has_hint(column, ITEM_NAME_HINTS):
            score += 1000.0
        if bool(item["is_numeric"]) and not _has_hint(
            column, ("id", "sku", "upc", "ean", "gtin")
        ):
            score -= 500.0
        candidates.append((score, column))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _infer_set_column(
    profiles: list[dict[str, Any]],
    *,
    item_column: str | None,
    period_column: str | None,
) -> str | None:
    candidates: list[tuple[float, str]] = []
    for item in profiles:
        column = str(item["column"])
        if column == item_column:
            continue
        unique_count = int(item["unique_count"])
        if unique_count < 2:
            continue
        score = 0.0
        if 2 <= unique_count <= 12:
            score += 500.0
        elif 13 <= unique_count <= 50:
            score += 150.0
        else:
            score -= float(unique_count)
        if _has_hint(column, SET_NAME_HINTS):
            score += 250.0
        if column == period_column:
            score -= 80.0
        if bool(item["is_numeric"]):
            score -= 300.0
        candidates.append((score, column))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _unique_values(
    frame: pl.DataFrame, column: str | None, *, limit: int = 200
) -> list[str]:
    if not column or column not in frame.schema:
        return []
    values = (
        frame.select(pl.col(column).cast(pl.Utf8).drop_nulls().unique().sort())
        .to_series()
        .to_list()
    )
    return [str(value) for value in values[:limit]]


def _default_selected_period(values: list[str]) -> str | None:
    if not values:
        return None
    normalized = {value.strip().lower(): value for value in values}
    for candidate in ("ac", "actual", "current"):
        if candidate in normalized:
            return normalized[candidate]
    return values[-1]


def _bool_option(value: Any, *, default: bool) -> bool:
    """Return a strict bool for recipe options that may arrive as strings."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _first_option(options: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = options.get(key)
        if value is not None and value != "" and value != [] and value != {}:
            return value
    return None


def build_recipe(
    input_path: Path,
    frame: pl.DataFrame,
    *,
    language: str = "en",
    existing_recipe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or merge a set-overlap recipe."""

    profiles = _column_profile(frame)
    mappings = dict((existing_recipe or {}).get("mappings") or {})
    period_column = mappings.get("period_column") or _infer_period_column(profiles)
    item_column = mappings.get("item_column") or _infer_item_column(profiles)
    set_column = mappings.get("set_column") or _infer_set_column(
        profiles,
        item_column=str(item_column) if item_column else None,
        period_column=str(period_column) if period_column else None,
    )
    if set_column == period_column:
        period_column = None
    dimensions = [
        item["column"]
        for item in profiles
        if item["column"] not in {item_column, set_column, period_column}
        and not item["is_numeric"]
    ][:6]
    period_values = _unique_values(frame, str(period_column) if period_column else None)
    options = dict((existing_recipe or {}).get("options") or {})
    small_multiples_dimension = _first_option(
        options,
        ("small_multiples_dimension", "small_multiple_dimension", "facet_column"),
    )
    recipe = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "source_file": str(input_path),
        "language": (existing_recipe or {}).get("language") or language,
        "mappings": {
            "item_column": item_column,
            "set_column": set_column,
            "period_column": period_column,
            "dimensions": mappings.get("dimensions") or dimensions,
        },
        "options": {
            "charts": options.get("charts") or ["upset", "venn"],
            "selected_period": options.get("selected_period")
            or _default_selected_period(period_values),
            "set_values": options.get("set_values") or [],
            "max_sets": int(options.get("max_sets") or 5),
            "min_intersection_size": int(options.get("min_intersection_size") or 1),
            "highlighted_sets": options.get("highlighted_sets") or [],
            "write_html": bool(options.get("write_html", True)),
            "aggregate_other_sets": _bool_option(
                options.get("aggregate_other_sets"), default=True
            ),
            "include_other_rank_with_explicit_sets": _bool_option(
                options.get("include_other_rank_with_explicit_sets"), default=False
            ),
            "small_multiples_dimension": (
                str(small_multiples_dimension) if small_multiples_dimension else None
            ),
            "small_multiples_max_panels": int(
                options.get("small_multiples_max_panels")
                or options.get("max_small_multiples")
                or DEFAULT_SMALL_MULTIPLES_MAX_PANELS
            ),
        },
        "inspection": {
            "row_count": frame.height,
            "column_count": frame.width,
            "columns": _column_names(frame),
            "schema": {name: str(dtype) for name, dtype in frame.schema.items()},
            "column_profiles": profiles,
            "period_values": period_values,
        },
    }
    if options.get("reporting_entity_label"):
        recipe["options"]["reporting_entity_label"] = str(
            options["reporting_entity_label"]
        )
    return validate_recipe(frame, recipe)


def validate_recipe(frame: pl.DataFrame, recipe: dict[str, Any]) -> dict[str, Any]:
    """Validate recipe mappings and options against ``frame``."""

    columns = set(_column_names(frame))
    mappings = recipe.setdefault("mappings", {})
    options = recipe.setdefault("options", {})
    item_column = mappings.get("item_column")
    set_column = mappings.get("set_column")
    if not item_column or item_column not in columns:
        raise ValueError("A valid mappings.item_column is required.")
    if not set_column or set_column not in columns:
        raise ValueError("A valid mappings.set_column is required.")
    period_column = mappings.get("period_column")
    if period_column and period_column not in columns:
        mappings["period_column"] = None
    charts = [
        str(chart).lower().replace("-", "_") for chart in options.get("charts") or []
    ]
    unsupported = [chart for chart in charts if chart not in SUPPORTED_CHARTS]
    if unsupported:
        raise ValueError("Unsupported set-overlap chart(s): " + ", ".join(unsupported))
    options["charts"] = charts or ["upset", "venn"]
    options["max_sets"] = max(2, int(options.get("max_sets") or 5))
    options["min_intersection_size"] = max(
        1, int(options.get("min_intersection_size") or 1)
    )
    options["small_multiples_max_panels"] = max(
        1,
        int(
            options.get("small_multiples_max_panels")
            or DEFAULT_SMALL_MULTIPLES_MAX_PANELS
        ),
    )
    options["aggregate_other_sets"] = _bool_option(
        options.get("aggregate_other_sets"), default=True
    )
    options["include_other_rank_with_explicit_sets"] = _bool_option(
        options.get("include_other_rank_with_explicit_sets"), default=False
    )
    options["set_values"] = [str(value) for value in options.get("set_values") or []]
    options["highlighted_sets"] = [
        str(value) for value in options.get("highlighted_sets") or []
    ]
    small_multiples_dimension = _first_option(
        options,
        ("small_multiples_dimension", "small_multiple_dimension", "facet_column"),
    )
    if small_multiples_dimension and str(small_multiples_dimension) in columns:
        options["small_multiples_dimension"] = str(small_multiples_dimension)
    else:
        options["small_multiples_dimension"] = None
    return recipe


def _ensure_legacy_import_path() -> None:
    """Make the shared legacy modules importable."""

    _activate_legacy_import_parent()


def _cleanup_legacy_imports() -> None:
    """Remove shared/vendored ``modules`` imports loaded for this plugin."""

    roots = [
        (SHARED_VENDOR_ROOT / "modules").resolve(),
        (VENDOR_ROOT / "modules").resolve(),
    ]
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            module_path = Path(module_file).resolve() if module_file else None
            if module_path and any(module_path.is_relative_to(root) for root in roots):
                del sys.modules[name]
    for root in (str(SHARED_VENDOR_ROOT), str(VENDOR_ROOT)):
        while root in sys.path:
            sys.path.remove(root)


def _apply_recipe_filters(
    frame: pl.DataFrame,
    recipe: dict[str, Any],
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Apply shared recipe filters when available."""

    _ensure_legacy_import_path()
    try:
        from modules.chart_harness.recipe_filters import apply_recipe_filters

        return apply_recipe_filters(frame, recipe)
    finally:
        _cleanup_legacy_imports()


def _preserve_recipe_filters(
    recipe: dict[str, Any],
    source_recipe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Preserve shared filter keys when the caller supplies a recipe."""

    _ensure_legacy_import_path()
    try:
        from modules.chart_harness.recipe_filters import preserve_recipe_filters

        return preserve_recipe_filters(recipe, source_recipe)
    finally:
        _cleanup_legacy_imports()


def _available_analysis_context(frame: pl.DataFrame) -> dict[str, Any]:
    """Return shared deterministic time/scenario availability metadata."""

    _ensure_legacy_import_path()
    try:
        from modules.chart_harness import available_analysis_context

        return available_analysis_context(frame)
    finally:
        _cleanup_legacy_imports()


def prepare_canonical_frame(
    frame: pl.DataFrame, recipe: dict[str, Any]
) -> pl.DataFrame:
    """Return canonical item/set/period membership rows."""

    mappings = recipe["mappings"]
    options = recipe["options"]
    item_column = str(mappings["item_column"])
    set_column = str(mappings["set_column"])
    period_column = mappings.get("period_column")
    facet_column = options.get("small_multiples_dimension")
    expressions = [
        pl.col(item_column).cast(pl.Utf8, strict=False).alias(CANONICAL_ITEM),
        pl.col(set_column).cast(pl.Utf8, strict=False).alias(CANONICAL_SET),
    ]
    if period_column:
        expressions.append(
            pl.col(str(period_column))
            .cast(pl.Utf8, strict=False)
            .fill_null(ALL_PERIOD_LABEL)
            .alias(CANONICAL_PERIOD)
        )
    else:
        expressions.append(pl.lit(ALL_PERIOD_LABEL).alias(CANONICAL_PERIOD))
    if facet_column:
        expressions.append(
            pl.col(str(facet_column))
            .cast(pl.Utf8, strict=False)
            .fill_null("Unspecified")
            .alias(CANONICAL_FACET)
        )
    canonical = (
        frame.select(expressions)
        .drop_nulls(subset=[CANONICAL_ITEM, CANONICAL_SET])
        .with_columns(
            [
                pl.col(CANONICAL_ITEM).str.strip_chars(),
                pl.col(CANONICAL_SET).str.strip_chars(),
                pl.col(CANONICAL_PERIOD).str.strip_chars(),
                *([pl.col(CANONICAL_FACET).str.strip_chars()] if facet_column else []),
            ]
        )
        .filter((pl.col(CANONICAL_ITEM) != "") & (pl.col(CANONICAL_SET) != ""))
        .unique()
    )
    if facet_column:
        canonical = canonical.with_columns(
            pl.when(pl.col(CANONICAL_FACET) == "")
            .then(pl.lit("Unspecified"))
            .otherwise(pl.col(CANONICAL_FACET))
            .alias(CANONICAL_FACET)
        )
    selected_period = options.get("selected_period")
    if period_column and selected_period:
        canonical = canonical.filter(pl.col(CANONICAL_PERIOD) == str(selected_period))
    if canonical.is_empty():
        raise ValueError("No item/set membership rows remain after filters.")
    return canonical


def _other_rank_label(rank_limit: int) -> str:
    return f"{OTHER_RANK_LABEL_PREFIX}{rank_limit}"


def _set_summary(frame: pl.DataFrame) -> pl.DataFrame:
    return (
        frame.group_by(CANONICAL_SET)
        .agg(pl.col(CANONICAL_ITEM).n_unique().alias("item_count"))
        .sort(["item_count", CANONICAL_SET], descending=[True, False])
        .with_row_index("rank", offset=1)
    )


def _rank_sets_for_upset(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    force_per_panel_ranking: bool = False,
) -> tuple[pl.DataFrame, pl.DataFrame, list[str], dict[str, Any]]:
    """Rank set values and optionally collapse lower ranks into Other."""

    options = recipe["options"]
    original_summary = _set_summary(canonical)
    rank_limit = int(options["max_sets"])
    explicit = (
        []
        if force_per_panel_ranking
        else [str(value) for value in options.get("set_values") or []]
    )
    available = set(original_summary[CANONICAL_SET].to_list())
    if explicit:
        missing = [value for value in explicit if value not in available]
        if missing:
            raise ValueError(
                "Requested set_values not found after filters/period selection: "
                + ", ".join(missing)
            )
        top_sets = [value for value in explicit if value in available]
        aggregate_other = bool(options.get("include_other_rank_with_explicit_sets"))
    else:
        top_sets = [
            str(value)
            for value in original_summary.head(rank_limit)[CANONICAL_SET].to_list()
        ]
        aggregate_other = bool(options.get("aggregate_other_sets"))

    lower_sets = [
        str(value)
        for value in original_summary[CANONICAL_SET].to_list()
        if str(value) not in set(top_sets)
    ]
    other_label = _other_rank_label(len(top_sets))
    ranked = canonical
    selected = list(top_sets)
    if aggregate_other and lower_sets:
        ranked = ranked.with_columns(
            pl.when(pl.col(CANONICAL_SET).is_in(lower_sets))
            .then(pl.lit(other_label))
            .otherwise(pl.col(CANONICAL_SET))
            .alias(CANONICAL_SET)
        )
        selected.append(other_label)
    else:
        ranked = ranked.filter(pl.col(CANONICAL_SET).is_in(selected))

    if ranked.is_empty() or len(selected) < 2:
        raise ValueError("Set-overlap charts require at least two populated sets.")

    ranked_summary = _set_summary(ranked)
    selected_order = {value: index for index, value in enumerate(selected, start=1)}
    original_rank = {
        str(row[CANONICAL_SET]): int(row["rank"]) for row in original_summary.to_dicts()
    }
    summary_rows: list[dict[str, Any]] = []
    for row in ranked_summary.to_dicts():
        set_name = str(row[CANONICAL_SET])
        is_other = set_name == other_label and bool(lower_sets)
        summary_rows.append(
            {
                "set": set_name,
                "item_count": int(row["item_count"]),
                "selected": set_name in selected_order,
                "rank": selected_order.get(set_name, int(row["rank"])),
                "original_rank": None if is_other else original_rank.get(set_name),
                "is_other_rank": is_other,
                "aggregated_set_count": len(lower_sets) if is_other else 0,
            }
        )
    summary_rows.sort(key=lambda row: int(row["rank"]))
    set_summary = pl.DataFrame(summary_rows)
    ranking_audit = {
        "rank_limit": rank_limit,
        "mode": "per_panel" if force_per_panel_ranking else "regular",
        "aggregate_other_sets": bool(aggregate_other),
        "other_rank_label": other_label if lower_sets and aggregate_other else None,
        "selected_sets": selected,
        "top_sets": top_sets,
        "aggregated_sets": lower_sets if aggregate_other else [],
        "available_set_count": original_summary.height,
    }
    return ranked, set_summary, selected, ranking_audit


def _item_sets_and_intersections(
    ranked_canonical: pl.DataFrame,
    selected: list[str],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    membership = (
        ranked_canonical.filter(pl.col(CANONICAL_SET).is_in(selected))
        .select([CANONICAL_ITEM, CANONICAL_SET])
        .unique()
    )
    item_sets = (
        membership.group_by(CANONICAL_ITEM)
        .agg(pl.col(CANONICAL_SET).unique().alias("sets"))
        .with_columns(
            [
                pl.col("sets").list.sort(),
                pl.col("sets").list.len().alias("set_count"),
            ]
        )
        .with_columns(pl.col("sets").list.join(" & ").alias("intersection"))
        .sort(CANONICAL_ITEM)
    )
    intersections = (
        item_sets.group_by(["intersection", "set_count"])
        .agg(pl.len().alias("item_count"))
        .sort(
            ["item_count", "set_count", "intersection"], descending=[True, True, False]
        )
    )
    return item_sets, intersections


def build_overlap_tables(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    list[str],
    dict[str, Any],
]:
    """Build deterministic set, item-membership and intersection tables."""

    ranked_canonical, set_summary, selected, ranking_audit = _rank_sets_for_upset(
        canonical, recipe
    )
    item_sets, intersections = _item_sets_and_intersections(ranked_canonical, selected)
    return (
        ranked_canonical,
        set_summary,
        item_sets,
        intersections,
        selected,
        ranking_audit,
    )


def _set_pair_table(item_sets: pl.DataFrame, selected_sets: list[str]) -> pl.DataFrame:
    """Return pairwise overlap counts for selected sets."""

    rows: list[dict[str, Any]] = []
    item_rows = item_sets.select([CANONICAL_ITEM, "sets"]).to_dicts()
    for left, right in combinations(selected_sets, 2):
        count = sum(
            1
            for row in item_rows
            if left in set(row["sets"]) and right in set(row["sets"])
        )
        rows.append({"left_set": left, "right_set": right, "item_count": count})
    return pl.DataFrame(rows)


def _normalize_artifact_mode(artifact_mode: str) -> str:
    """Return a supported artifact mode or raise for invalid contract input."""

    normalized = str(artifact_mode or ARTIFACT_MODE_DATA_AND_RENDER).strip().lower()
    if normalized not in ARTIFACT_MODES:
        allowed = ", ".join(sorted(ARTIFACT_MODES))
        raise ValueError(f"Unsupported artifact_mode {artifact_mode!r}; use {allowed}.")
    return normalized


def _chart_title_lines(recipe: dict[str, Any], *, chart_name: str) -> list[str]:
    mappings = recipe["mappings"]
    options = recipe["options"]
    period = options.get("selected_period") or ALL_PERIOD_LABEL
    first_line = reporting_subject_label_from_recipe(recipe)
    return [
        line
        for line in (
            first_line,
            f"{chart_name}: {mappings['item_column']} overlap by {mappings['set_column']}",
            str(period),
        )
        if line
    ]


def _chart_title(recipe: dict[str, Any], *, chart_name: str, html: bool = False) -> str:
    lines = _chart_title_lines(recipe, chart_name=chart_name)
    if html and len(lines) >= 3:
        return reporting_title_html(lines[0], lines[1], lines[2])
    return "\n".join(lines)


def _small_multiple_panel_title(
    recipe: dict[str, Any],
    *,
    facet_dimension: str,
    facet_value: str,
    html_title: bool = False,
) -> str:
    mappings = recipe["mappings"]
    options = recipe["options"]
    period = options.get("selected_period") or ALL_PERIOD_LABEL
    lines = [
        f"{facet_dimension}: {facet_value}",
        f"UpSet: {mappings['item_column']} overlap by {mappings['set_column']}",
        str(period),
    ]
    if html_title:
        return reporting_title_html(lines[0], lines[1], lines[2])
    return "\n".join(lines)


def _apply_upset_reporting_title(fig: Any, title_html: str) -> None:
    """Apply the compact three-row reporting title used by UpSet exports."""

    existing_margin = fig.layout.margin.to_plotly_json() if fig.layout.margin else {}
    margin = {
        "l": int(existing_margin.get("l") or 35),
        "r": int(existing_margin.get("r") or 25),
        "t": max(int(existing_margin.get("t") or 0), UPSET_TITLE_TOP_MARGIN),
        "b": max(int(existing_margin.get("b") or 0), UPSET_TITLE_BOTTOM_MARGIN),
    }
    fig.update_layout(
        title={
            "text": title_html,
            "x": 0.01,
            "xanchor": "left",
            "y": UPSET_TITLE_Y,
            "yanchor": "top",
            "font": {"size": UPSET_TITLE_FONT_SIZE, "color": UPSET_TITLE_COLOR},
        },
        margin=margin,
    )


def _facet_values_for_small_multiples(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
) -> list[str]:
    if CANONICAL_FACET not in canonical.schema:
        return []
    max_panels = int(recipe["options"].get("small_multiples_max_panels") or 1)
    rows = (
        canonical.group_by(CANONICAL_FACET)
        .agg(pl.col(CANONICAL_ITEM).n_unique().alias("item_count"))
        .sort(["item_count", CANONICAL_FACET], descending=[True, False])
        .head(max_panels)
        .to_dicts()
    )
    return [str(row[CANONICAL_FACET]) for row in rows]


def _requested_palette_name(
    recipe: Mapping[str, Any],
    color_dict: Mapping[str, Any],
    default_name: str,
) -> str:
    """Return the requested chart palette, falling back to the default palette."""

    def is_palette_value(value: Any) -> bool:
        return isinstance(value, (list, tuple)) and any(
            isinstance(color, str) for color in value
        )

    options = recipe.get("options")
    requested: str | None = None
    if isinstance(options, Mapping):
        for key in PALETTE_OPTION_KEYS:
            value = options.get(key)
            if isinstance(value, str) and value.strip():
                requested = value.strip()
                break

    if requested:
        if requested in color_dict and is_palette_value(color_dict[requested]):
            return requested
        requested_lower = requested.lower()
        for palette_name, palette in color_dict.items():
            if str(palette_name).lower() == requested_lower and is_palette_value(
                palette
            ):
                return str(palette_name)

    if default_name in color_dict and is_palette_value(color_dict[default_name]):
        return default_name
    for palette_name, palette in color_dict.items():
        if is_palette_value(palette):
            return str(palette_name)
    return default_name


def _venn_colors_from_palette(
    palette: Any,
    selected_set_count: int,
) -> tuple[str, ...]:
    """Return enough Venn colors from a legacy chart palette."""

    colors = [str(color) for color in palette if isinstance(color, str) and color]
    fallback_index = 0
    while len(colors) < selected_set_count:
        colors.append(VENN_FALLBACK_COLORS[fallback_index % len(VENN_FALLBACK_COLORS)])
        fallback_index += 1
    return tuple(colors[:selected_set_count])


def _resolve_chart_palette(
    recipe: Mapping[str, Any],
    selected_set_count: int,
) -> tuple[str, tuple[str, ...]]:
    """Resolve the plugin chart palette through the shared legacy palette map."""

    _ensure_legacy_import_path()
    try:
        from modules.charting.chart_primitives import get_color_dictionary
        from modules.utilities.config import get_naming_params

        names = get_naming_params()
        color_dict = get_color_dictionary({})
        palette_name = _requested_palette_name(
            recipe,
            color_dict,
            names["bainColorpalette"],
        )
        return (
            palette_name,
            _venn_colors_from_palette(color_dict[palette_name], selected_set_count),
        )
    except (ImportError, ModuleNotFoundError, KeyError, TypeError, ValueError) as exc:
        LOGGER.debug("Falling back to default Venn colors: %s", exc)
        return (
            "fallback",
            _venn_colors_from_palette(VENN_FALLBACK_COLORS, selected_set_count),
        )
    finally:
        _cleanup_legacy_imports()


def _make_upset_figure(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    selected_sets: list[str],
) -> tuple[Any, str, dict[str, Any]]:
    """Return one UpSet Plotly figure from already-ranked canonical rows."""

    _ensure_legacy_import_path()
    try:
        from modules.charting.chart_primitives import get_color_dictionary
        from modules.charting.upset_helpers import build_upset_matrix
        from modules.charting.upset_plot import plot_upset
        from modules.utilities.config import get_naming_params

        names = get_naming_params()
        color_dict = get_color_dictionary({})
        palette_name = _requested_palette_name(
            recipe,
            color_dict,
            names["bainColorpalette"],
        )
        mapping = (
            canonical.filter(pl.col(CANONICAL_SET).is_in(selected_sets))
            .select(
                [
                    pl.col(CANONICAL_ITEM).alias("Name"),
                    pl.col(CANONICAL_SET).alias("set"),
                ]
            )
            .lazy()
        )
        matrix = build_upset_matrix(mapping, selected_sets)
        chart_dict = {
            names["minIntersectionSize"]: int(
                recipe["options"].get("min_intersection_size") or 1
            ),
            names["highlightedDimension"]: recipe["options"].get("highlighted_sets")
            or [],
            names["colorChoice"]: names["redToGreen"],
            names["colorpalette"]: palette_name,
        }
        return (
            plot_upset(matrix, chart_dict),
            palette_name,
            {
                "chart_dict": chart_dict,
                "source_functions": [
                    "modules.charting.upset_helpers.build_upset_matrix",
                    "modules.charting.upset_plot.plot_upset",
                ],
            },
        )
    finally:
        _cleanup_legacy_imports()


def _write_upset_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    selected_sets: list[str],
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Write UpSet PNG/HTML artifacts through the legacy matrix/Plotly helper."""

    if not render:
        return [], {
            "chart": "upset",
            "status": "data_written",
            "title": _chart_title(recipe, chart_name="UpSet"),
            "artifacts": [],
            "selected_sets": selected_sets,
            "renderer": "not_rendered",
            "source_functions": [
                "modules.charting.upset_helpers.build_upset_matrix",
                "modules.charting.upset_plot.plot_upset",
            ],
        }
    _ensure_legacy_import_path()
    paths: list[str] = []
    try:
        fig, palette_name, figure_audit = _make_upset_figure(
            canonical, recipe, selected_sets
        )
        title = _chart_title(recipe, chart_name="UpSet")
        title_html = _chart_title(recipe, chart_name="UpSet", html=True)
        _apply_upset_reporting_title(fig, title_html)
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font={"family": "Arial", "size": 12, "color": "#1F2328"},
        )
        export_fig, normalization_audit = normalize_plotly_figure_for_static_export(fig)
        html_path = output_dir / "upset.html"
        if bool(recipe["options"].get("write_html", True)):
            export_fig.write_html(str(html_path), include_plotlyjs="cdn")
            paths.append(str(html_path))
        png_path = output_dir / "upset.png"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                export_width = int(export_fig.layout.width or 1000)
                export_height = int(export_fig.layout.height or 650)
                export_fig.write_image(
                    str(png_path),
                    format="png",
                    width=export_width,
                    height=export_height,
                )
            paths.append(str(png_path))
            status = "written"
            renderer = "plotly+kaleido"
            error = None
        except (OSError, RuntimeError, ValueError) as exc:
            status = "written_html_only" if paths else "not_written"
            renderer = "plotly_html"
            error = str(exc)
        return paths, {
            "chart": "upset",
            "status": status,
            "title": title,
            "artifacts": [Path(path).name for path in paths],
            "selected_sets": selected_sets,
            "palette": palette_name,
            "chart_font_size": SET_OVERLAP_CHART_FONT_SIZE,
            "renderer": renderer,
            "error": error,
            "figure_export_normalization": normalization_audit,
            "source_functions": figure_audit["source_functions"],
        }
    finally:
        _cleanup_legacy_imports()


def _write_upset_small_multiples_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Write a stacked HTML small-multiple UpSet artifact."""

    facet_dimension = recipe["options"].get("small_multiples_dimension")
    if not facet_dimension or CANONICAL_FACET not in canonical.schema:
        return [], {
            "chart": "upset_small_multiples",
            "status": "not_written_missing_facet",
            "reason": "small_multiples_dimension is not set or is unavailable.",
        }

    facets = _facet_values_for_small_multiples(canonical, recipe)
    if not facets:
        return [], {
            "chart": "upset_small_multiples",
            "status": "not_written_no_facets",
            "small_multiples_dimension": facet_dimension,
        }

    panel_html: list[str] = []
    panel_audits: list[dict[str, Any]] = []
    set_summary_rows: list[dict[str, Any]] = []
    intersection_rows: list[dict[str, Any]] = []
    paths: list[str] = []
    for facet_value in facets:
        panel_canonical = canonical.filter(pl.col(CANONICAL_FACET) == facet_value)
        try:
            ranked, set_summary, selected_sets, ranking = _rank_sets_for_upset(
                panel_canonical,
                recipe,
                force_per_panel_ranking=True,
            )
            item_sets, intersections = _item_sets_and_intersections(
                ranked,
                selected_sets,
            )
        except ValueError as exc:
            panel_audits.append(
                {
                    "facet": facet_value,
                    "status": "not_written",
                    "error": str(exc),
                }
            )
            continue

        for row in set_summary.to_dicts():
            set_summary_rows.append({"facet": facet_value, **row})
        for row in intersections.to_dicts():
            intersection_rows.append({"facet": facet_value, **row})

        if not render:
            panel_audits.append(
                {
                    "facet": facet_value,
                    "status": "data_written",
                    "selected_sets": selected_sets,
                    "set_ranking": ranking,
                    "item_count": item_sets.height,
                    "intersection_count": intersections.height,
                    "source_functions": [
                        "modules.charting.upset_helpers.build_upset_matrix",
                        "modules.charting.upset_plot.plot_upset",
                    ],
                }
            )
            continue

        fig, palette_name, figure_audit = _make_upset_figure(
            ranked,
            recipe,
            selected_sets,
        )
        panel_title = _small_multiple_panel_title(
            recipe,
            facet_dimension=str(facet_dimension),
            facet_value=facet_value,
            html_title=True,
        )
        _apply_upset_reporting_title(fig, panel_title)
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font={"family": "Arial", "size": 12, "color": "#1F2328"},
        )
        panel_html.append(
            '<section class="upset-panel">'
            + fig.to_html(
                full_html=False,
                include_plotlyjs="cdn" if not panel_html else False,
                config={"responsive": True},
            )
            + "</section>"
        )
        panel_audits.append(
            {
                "facet": facet_value,
                "status": "written",
                "selected_sets": selected_sets,
                "set_ranking": ranking,
                "item_count": item_sets.height,
                "intersection_count": intersections.height,
                "palette": palette_name,
                "source_functions": figure_audit["source_functions"],
            }
        )

    if set_summary_rows:
        summary_path = output_dir / "set_overlap_small_multiples_set_summary.csv"
        write_csv(summary_path, pl.DataFrame(set_summary_rows))
        paths.append(str(summary_path))
    if intersection_rows:
        intersections_path = (
            output_dir / "set_overlap_small_multiples_intersections.csv"
        )
        write_csv(intersections_path, pl.DataFrame(intersection_rows))
        paths.append(str(intersections_path))
    if not render:
        return paths, {
            "chart": "upset_small_multiples",
            "status": "data_written" if panel_audits else "not_written_no_valid_panels",
            "title": _chart_title(recipe, chart_name="UpSet small multiples"),
            "artifacts": [Path(path).name for path in paths],
            "small_multiples_dimension": facet_dimension,
            "panel_count": len(panel_audits),
            "requested_panel_count": len(facets),
            "per_panel_ranking": True,
            "facets": panel_audits,
            "renderer": "not_rendered",
            "source_functions": [
                "modules.charting.upset_helpers.build_upset_matrix",
                "modules.charting.upset_plot.plot_upset",
            ],
        }
    if not panel_html:
        return paths, {
            "chart": "upset_small_multiples",
            "status": "not_written_no_valid_panels",
            "small_multiples_dimension": facet_dimension,
            "facets": panel_audits,
        }

    page_title = _chart_title(recipe, chart_name="UpSet small multiples")
    html_path = output_dir / "upset_small_multiples.html"
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html>",
                "<head>",
                '<meta charset="utf-8">',
                f"<title>{html.escape(page_title)}</title>",
                "<style>",
                "body{font-family:Arial,sans-serif;font-size:12px;color:#1F2328;background:#fff;margin:0;padding:16px}",
                ".upset-small-multiples{display:inline-block;padding:8px 18px 18px 8px}",
                "h1{font-size:12px;line-height:1.25;margin:0 0 16px;font-weight:700;white-space:pre-line}",
                ".upset-panel{break-inside:avoid;margin:0 0 24px}",
                "</style>",
                "</head>",
                "<body>",
                '<main class="upset-small-multiples" data-gallery-screenshot>',
                f"<h1>{html.escape(page_title)}</h1>",
                *panel_html,
                "</main>",
                "</body>",
                "</html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths.append(str(html_path))
    return paths, {
        "chart": "upset_small_multiples",
        "status": "written",
        "title": page_title,
        "artifacts": [Path(path).name for path in paths],
        "small_multiples_dimension": facet_dimension,
        "panel_count": len(panel_html),
        "requested_panel_count": len(facets),
        "per_panel_ranking": True,
        "chart_font_size": SET_OVERLAP_CHART_FONT_SIZE,
        "facets": panel_audits,
        "renderer": "plotly_html",
    }


def _write_venn_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    selected_sets: list[str],
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Write a Venn PNG for two or three selected sets."""

    if len(selected_sets) not in {2, 3}:
        return [], {
            "chart": "venn",
            "status": "not_written_unsupported_set_count",
            "reason": "Venn charts are only readable for two or three sets.",
            "selected_set_count": len(selected_sets),
            "selected_sets": selected_sets,
        }
    if not render:
        return [], {
            "chart": "venn",
            "status": "data_written",
            "title": _chart_title(recipe, chart_name="Venn"),
            "artifacts": [],
            "selected_sets": selected_sets,
            "renderer": "not_rendered",
            "source_functions": [
                "modules.data.misc_charts_data_prep.prepare_data_for_venn_plot",
                "modules.charting.draw_venn_upset.draw_venn_chart",
            ],
        }
    try:
        cache_dir = Path(tempfile.gettempdir()) / "mparanza-matplotlib-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib_venn import venn2, venn3
    except (ImportError, ModuleNotFoundError) as exc:
        return [], {
            "chart": "venn",
            "status": "not_written_missing_dependency",
            "error": str(exc),
        }

    membership = (
        canonical.filter(pl.col(CANONICAL_SET).is_in(selected_sets))
        .select([CANONICAL_ITEM, CANONICAL_SET])
        .unique()
    )
    grouped = membership.group_by(CANONICAL_SET).agg(
        pl.col(CANONICAL_ITEM).unique().alias("items")
    )
    set_payload = {
        str(row[CANONICAL_SET]): set(str(item) for item in row["items"])
        for row in grouped.to_dicts()
    }
    data = [set_payload.get(name, set()) for name in selected_sets]
    palette_name, set_colors = _resolve_chart_palette(recipe, len(selected_sets))
    fig, ax = plt.subplots(
        figsize=(
            VENN_EXPORT_WIDTH / VENN_EXPORT_DPI,
            VENN_EXPORT_HEIGHT / VENN_EXPORT_DPI,
        ),
        facecolor="white",
    )
    fig.subplots_adjust(left=0.06, right=0.97, top=0.76, bottom=0.08)
    if len(selected_sets) == 2:
        venn = venn2(
            data,
            set_labels=tuple(selected_sets),
            set_colors=set_colors,
            alpha=0.55,
            ax=ax,
        )
    else:
        venn = venn3(
            data,
            set_labels=tuple(selected_sets),
            set_colors=set_colors,
            alpha=0.55,
            ax=ax,
        )
    if venn is not None:
        for text in [*venn.set_labels, *venn.subset_labels]:
            if text is not None:
                text.set_fontfamily("Arial")
                text.set_fontsize(SET_OVERLAP_CHART_FONT_SIZE)
                text.set_color("#1F2328")
    title = _chart_title(recipe, chart_name="Venn")
    fig.text(
        0.04,
        0.96,
        title,
        ha="left",
        va="top",
        fontfamily="Arial",
        fontsize=SET_OVERLAP_CHART_FONT_SIZE,
        color="#1F2328",
    )
    png_path = output_dir / "venn.png"
    fig.savefig(png_path, dpi=VENN_EXPORT_DPI, facecolor="white")
    plt.close(fig)
    return [str(png_path)], {
        "chart": "venn",
        "status": "written",
        "title": title,
        "artifacts": [png_path.name],
        "selected_sets": selected_sets,
        "palette": palette_name,
        "colors": list(set_colors),
        "chart_font_size": SET_OVERLAP_CHART_FONT_SIZE,
        "dimensions": {"width": VENN_EXPORT_WIDTH, "height": VENN_EXPORT_HEIGHT},
        "renderer": "matplotlib_venn",
        "source_functions": [
            "modules.data.misc_charts_data_prep.prepare_data_for_venn_plot",
            "modules.charting.draw_venn_upset.draw_venn_chart",
        ],
    }


def inspect_set_overlap_inputs(
    input_path: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
) -> InspectionResult:
    """Inspect inputs and write suggested recipe files."""

    frame = read_table(input_path)
    existing_recipe = read_json(recipe_path)
    recipe = build_recipe(
        input_path,
        frame,
        language=language,
        existing_recipe=existing_recipe,
    )
    recipe = _preserve_recipe_filters(recipe, existing_recipe)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "input_file": str(input_path),
        "row_count": frame.height,
        "column_count": frame.width,
        "columns": _column_names(frame),
        "schema": {name: str(dtype) for name, dtype in frame.schema.items()},
        "available_analysis_context": _available_analysis_context(frame),
        "suggested_mappings": recipe["mappings"],
        "suggested_options": recipe["options"],
        "column_profiles": recipe["inspection"]["column_profiles"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "inspection.json", payload)
    write_json(output_dir / "suggested_recipe.json", recipe)
    return InspectionResult(payload=payload, recipe=recipe, output_dir=output_dir)


def run_set_overlap(
    input_path: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: str = "en",
    artifact_mode: str = ARTIFACT_MODE_DATA_AND_RENDER,
) -> SetOverlapRunResult:
    """Run deterministic Venn/UpSet overlap analysis."""

    artifact_mode = _normalize_artifact_mode(artifact_mode)
    frame = read_table(input_path)
    existing_recipe = read_json(recipe_path)
    recipe = build_recipe(
        input_path,
        frame,
        language=language,
        existing_recipe=existing_recipe,
    )
    recipe = _preserve_recipe_filters(recipe, existing_recipe)
    recipe = validate_recipe(frame, recipe)
    filtered, filter_audit = _apply_recipe_filters(frame, recipe)
    recipe.setdefault("options", {})["recipe_filter_audit"] = filter_audit
    canonical = prepare_canonical_frame(filtered, recipe)
    (
        ranked_canonical,
        set_summary,
        item_sets,
        intersections,
        selected_sets,
        ranking_audit,
    ) = build_overlap_tables(canonical, recipe)
    pair_table = _set_pair_table(item_sets, selected_sets)

    output_dir.mkdir(parents=True, exist_ok=True)
    run_intake = write_run_intake(
        output_dir,
        input_path,
        recipe_path=recipe_path,
        recipe=recipe,
        source_row_count=frame.height,
    )
    canonical_path = output_dir / "set_overlap_canonical.csv"
    ranked_canonical_path = output_dir / "set_overlap_ranked_canonical.csv"
    set_summary_path = output_dir / "set_overlap_set_summary.csv"
    item_sets_path = output_dir / "set_overlap_item_sets.csv"
    intersections_path = output_dir / "set_overlap_intersections.csv"
    pair_path = output_dir / "set_overlap_pairs.csv"
    write_csv(canonical_path, canonical)
    write_csv(ranked_canonical_path, ranked_canonical)
    write_csv(set_summary_path, set_summary)
    write_csv(item_sets_path, item_sets)
    write_csv(intersections_path, intersections)
    write_csv(pair_path, pair_table)

    artifact_paths = [
        str(canonical_path),
        str(ranked_canonical_path),
        str(set_summary_path),
        str(item_sets_path),
        str(intersections_path),
        str(pair_path),
    ]
    chart_audits: dict[str, Any] = {}
    chart_names = [
        str(chart)
        for chart in recipe["options"].get("charts") or []
        if str(chart) in SUPPORTED_CHARTS
    ]
    charts = set(chart_names)
    render_charts = artifact_mode != ARTIFACT_MODE_DATA_ONLY

    if "upset" in charts:
        paths, chart_audit = _write_upset_chart(
            ranked_canonical, recipe, output_dir, selected_sets, render=render_charts
        )
        artifact_paths.extend(paths)
        chart_audits["upset"] = chart_audit
    if "upset_small_multiples" in charts:
        paths, chart_audit = _write_upset_small_multiples_chart(
            canonical,
            recipe,
            output_dir,
            render=render_charts,
        )
        artifact_paths.extend(paths)
        chart_audits["upset_small_multiples"] = chart_audit
    if "venn" in charts:
        paths, chart_audit = _write_venn_chart(
            ranked_canonical, recipe, output_dir, selected_sets, render=render_charts
        )
        artifact_paths.extend(paths)
        chart_audits["venn"] = chart_audit
    context = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "analysis_type": "set_overlap",
        "source_file": str(input_path),
        "language": recipe.get("language") or language,
        "artifact_mode": artifact_mode,
        "mappings": recipe["mappings"],
        "options": recipe["options"],
        "recipe_filters": filter_audit,
        "selected_sets": selected_sets,
        "row_counts": {
            "source": frame.height,
            "filtered": filtered.height,
            "canonical_memberships": canonical.height,
            "ranked_canonical_memberships": ranked_canonical.height,
            "item_count": item_sets.height,
            "intersection_count": intersections.height,
        },
        "set_summary": set_summary.to_dicts(),
        "set_ranking": ranking_audit,
        "intersections": intersections.to_dicts(),
        "pairwise_overlap": pair_table.to_dicts(),
        "chart_audits": chart_audits,
        "codex_interpretation_contract": {
            "must_review_when_written": True,
            "required_points": [
                "State the selected item column, set column, period and filters.",
                "Identify the largest exact intersections from set_overlap_intersections.csv.",
                "Use UpSet for more than three sets; use Venn only as a simple communication aid for two or three sets.",
            ],
        },
    }
    context_path = output_dir / "set_overlap_context.json"
    used_recipe_path = output_dir / "used_recipe.json"
    write_json(context_path, context)
    write_json(used_recipe_path, recipe)
    artifact_paths.extend([str(context_path), str(used_recipe_path)])

    audit = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "created_at": utc_now(),
        "input_file": str(input_path),
        "recipe": recipe,
        "artifact_mode": artifact_mode,
        "checks": {
            "source_row_count": frame.height,
            "filtered_row_count": filtered.height,
            "canonical_row_count": canonical.height,
            "selected_set_count": len(selected_sets),
            "legacy_chart_attempt_count": len(chart_audits),
            "legacy_chart_written_count": sum(
                1
                for item in chart_audits.values()
                if item.get("status") in {"written", "written_html_only"}
            ),
            "legacy_chart_data_count": sum(
                1
                for item in chart_audits.values()
                if item.get("status")
                in {"written", "written_html_only", "data_written"}
            ),
        },
        "charts": chart_audits,
        "outputs": {
            Path(path).relative_to(output_dir).as_posix(): "written"
            for path in artifact_paths
            if Path(path).exists() and Path(path).is_file()
        },
    }
    audit_path = output_dir / "set_overlap_audit.json"
    write_json(audit_path, audit)
    artifact_paths.append(str(audit_path))
    zip_path = output_dir / "set_overlap_artifacts.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifact_paths:
            path = Path(artifact)
            if path.exists() and path.is_file():
                archive.write(path, path.relative_to(output_dir))
    artifact_paths.append(str(zip_path))
    review_session = write_review_session_artifacts(
        output_dir,
        input_path,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        recipe_path=recipe_path,
        recipe=recipe,
        context=context,
        audit=audit,
    )
    audit["review_session"] = {
        "run_id": review_session.run_id,
        "run_intake_path": str(review_session.run_intake_path),
        "review_payload_path": str(review_session.review_payload_path),
        "ui_decisions_path": str(review_session.ui_decisions_path),
        "final_artifacts_path": str(review_session.final_artifacts_path),
        "review_item_count": review_session.review_item_count,
    }
    write_json(audit_path, audit)
    return SetOverlapRunResult(
        canonical_frame=canonical,
        context=context,
        audit=audit,
        artifact_paths=artifact_paths,
        review_session=audit["review_session"],
    )
