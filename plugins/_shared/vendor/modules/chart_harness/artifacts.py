"""Common deterministic artifact plumbing for chart-family plugins."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import polars as pl

from modules.utilities.helpers import get_schema_and_column_names
from modules.utilities.utils import get_row_count

__all__ = [
    "CSV_EXTENSIONS",
    "EXCEL_EXTENSIONS",
    "SCHEMA_VERSION",
    "artifact_kind",
    "analysis_scope_from_recipe",
    "build_manifest_artifacts",
    "frame_profile",
    "json_safe",
    "read_json_object",
    "read_table",
    "relative_path",
    "utc_now",
    "write_json",
    "write_prepared_data_manifest",
]

SCHEMA_VERSION = "1.0"
CSV_EXTENSIONS = {".csv", ".tsv", ".psv", ".txt"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
FILTER_INCLUDE_KEYS = ("include", "includes", "in", "values", "eq", "equals", "only")
FILTER_EXCLUDE_KEYS = (
    "exclude",
    "excludes",
    "not_in",
    "not",
    "neq",
    "not_equals",
)
FILTER_GREATER_THAN_KEYS = ("gt", "greater_than", "above", "min_exclusive")
FILTER_GREATER_EQUAL_KEYS = (
    "gte",
    "ge",
    "greater_than_or_equal",
    "at_least",
    "minimum",
    "min",
)
FILTER_LESS_THAN_KEYS = ("lt", "less_than", "below", "max_exclusive")
FILTER_LESS_EQUAL_KEYS = (
    "lte",
    "le",
    "less_than_or_equal",
    "at_most",
    "maximum",
    "max",
)
LEGACY_FILTER_INCLUDE_KEY = "toIncludeItems"
LEGACY_FILTER_EXCLUDE_KEY = "toExcludeItems"


def utc_now() -> str:
    """Return the current UTC timestamp for audit metadata."""

    return datetime.now(UTC).isoformat()


def json_safe(value: Any) -> Any:
    """Return JSON-safe values for stable artifact files."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (Path, datetime, date)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, TypeError, ValueError):
            return str(value)
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write stable, UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json_object(path: Path | None) -> dict[str, Any] | None:
    """Read a JSON object from ``path`` when one is provided."""

    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _collect_csv_scan(path: Path, *, separator: str) -> pl.DataFrame:
    """Read delimited input through a lazy scan and collect once."""

    lf = pl.scan_csv(path, separator=separator, infer_schema_length=10000)
    try:
        return lf.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return lf.collect()


def read_table(path: Path) -> pl.DataFrame:
    """Read supported delimited or Excel tabular inputs into Polars."""

    suffix = path.suffix.lower()
    if suffix in CSV_EXTENSIONS:
        separator = {".tsv": "\t", ".psv": "|"}.get(suffix, ",")
        return _collect_csv_scan(path, separator=separator)
    if suffix in EXCEL_EXTENSIONS:
        return pl.read_excel(path)
    raise ValueError(
        f"Unsupported input file type '{suffix}'. Use CSV, TSV, PSV, XLSX, XLSM, or XLS."
    )


def relative_path(path: Path, base: Path) -> str:
    """Return a POSIX relative path when ``path`` is inside ``base``."""

    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def artifact_kind(path: Path) -> str:
    """Return the normalized singular artifact kind for a generated file."""

    suffix = path.suffix.lower()
    if suffix in {".png", ".html", ".htm"}:
        return "chart"
    if suffix in {".csv", ".xlsx", ".xlsm"}:
        return "table"
    if suffix == ".json":
        return "context"
    if suffix == ".md":
        return "brief"
    if suffix == ".docx":
        return "report"
    return "file"


def _is_present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _first_present(source: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if _is_present(value):
            return value
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None or value is False or value == []:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _filter_identity_from_audit(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    filters = audit.get("filters")
    if not isinstance(filters, list):
        return []
    result: list[dict[str, Any]] = []
    for item in filters:
        if not isinstance(item, Mapping) or not _is_present(item.get("column")):
            continue
        step: dict[str, Any] = {"column": str(item["column"])}
        include = _as_list(item.get("include"))
        exclude = _as_list(item.get("exclude"))
        if include:
            step["include"] = include
        if exclude:
            step["exclude"] = exclude
        _copy_filter_comparisons(step, item)
        if len(step) > 1:
            result.append(step)
    return result


def _normalize_filter_rule(column: str, rules: Any) -> dict[str, Any]:
    if isinstance(rules, Mapping):
        include = _first_present(
            rules, (*FILTER_INCLUDE_KEYS, LEGACY_FILTER_INCLUDE_KEY)
        )
        exclude = _first_present(
            rules, (*FILTER_EXCLUDE_KEYS, LEGACY_FILTER_EXCLUDE_KEY)
        )
        greater_than = _first_present(rules, FILTER_GREATER_THAN_KEYS)
        greater_equal = _first_present(rules, FILTER_GREATER_EQUAL_KEYS)
        less_than = _first_present(rules, FILTER_LESS_THAN_KEYS)
        less_equal = _first_present(rules, FILTER_LESS_EQUAL_KEYS)
    else:
        include = rules
        exclude = None
        greater_than = None
        greater_equal = None
        less_than = None
        less_equal = None
    rule: dict[str, Any] = {"column": column}
    include_values = _as_list(include)
    exclude_values = _as_list(exclude)
    if include_values:
        rule["include"] = include_values
    if exclude_values:
        rule["exclude"] = exclude_values
    _copy_present_comparison(rule, "gt", greater_than)
    _copy_present_comparison(rule, "gte", greater_equal)
    _copy_present_comparison(rule, "lt", less_than)
    _copy_present_comparison(rule, "lte", less_equal)
    return rule


def _copy_filter_comparisons(
    target: dict[str, Any],
    source: Mapping[str, Any],
) -> None:
    for key in ("gt", "gte", "lt", "lte"):
        _copy_present_comparison(target, key, source.get(key))


def _copy_present_comparison(
    target: dict[str, Any],
    key: str,
    value: Any,
) -> None:
    if value is None or value == "" or value == [] or value == {}:
        return
    values = _as_list(value)
    if len(values) == 1:
        target[key] = values[0]


def _normalize_filter_payload(filters: Any) -> list[dict[str, Any]]:
    if filters is None or filters is False or filters == {} or filters == []:
        return []
    if isinstance(filters, Mapping):
        return [
            rule
            for column, rules in filters.items()
            if column
            for rule in [_normalize_filter_rule(str(column), rules)]
            if len(rule) > 1
        ]
    if isinstance(filters, list):
        normalized: list[dict[str, Any]] = []
        for item in filters:
            if not isinstance(item, Mapping):
                continue
            if "column" in item and item["column"]:
                rule = _normalize_filter_rule(str(item["column"]), item)
            elif len(item) == 1:
                column, rules = next(iter(item.items()))
                if not column:
                    continue
                rule = _normalize_filter_rule(str(column), rules)
            else:
                continue
            if len(rule) > 1:
                normalized.append(rule)
        return normalized
    return []


def _filter_identity_from_recipe(
    recipe: Mapping[str, Any],
    options: Mapping[str, Any],
) -> list[dict[str, Any]]:
    # Filter identity is deterministic because filters select the exact row
    # population. Prefer the applied filter audit when a plugin has written one;
    # otherwise normalize request aliases into the same include/exclude shape.
    audit = options.get("recipe_filter_audit")
    if isinstance(audit, Mapping):
        audited = _filter_identity_from_audit(audit)
        if audited:
            return audited
    filters: list[dict[str, Any]] = []
    root_filter = _first_present(recipe, ("filters", "filter_dict"))
    if root_filter is not None:
        filters.extend(_normalize_filter_payload(root_filter))
    options_filter = _first_present(options, ("filters", "filter_dict"))
    if options_filter is not None:
        filters.extend(_normalize_filter_payload(options_filter))
    return filters


def _copy_present_keys(
    target: dict[str, Any],
    source: Mapping[str, Any],
    keys: Iterable[str],
) -> None:
    for key in keys:
        value = source.get(key)
        if _is_present(value):
            target[key] = value


def _normalize_time_window(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    _copy_present_keys(
        result,
        value,
        (
            "mode",
            "window_type",
            "calendar",
            "calendar_type",
            "grain",
            "period_grain",
            "time_grain",
            "date_column",
            "start_date",
            "end_date",
            "fiscal_start_month",
            "rolling_window_months",
            "rolling_comparison",
        ),
    )
    for side in ("baseline", "comparison"):
        side_value = value.get(side)
        if isinstance(side_value, Mapping):
            normalized_side: dict[str, Any] = {}
            _copy_present_keys(
                normalized_side,
                side_value,
                ("label", "start_date", "end_date", "period", "scenario"),
            )
            if normalized_side:
                result[side] = normalized_side
    return result


def _time_window_from_options(options: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    period_window = _normalize_time_window(options.get("period_window"))
    if period_window:
        result.update(period_window)
    _copy_present_keys(
        result,
        options,
        (
            "period_comparison_mode",
            "calendar",
            "calendar_type",
            "grain",
            "period_grain",
            "time_grain",
            "fiscal_start_month",
            "rolling_window_months",
            "rolling_comparison",
            "start_date",
            "end_date",
            "baseline_start_date",
            "baseline_end_date",
            "comparison_start_date",
            "comparison_end_date",
        ),
    )
    if "period_comparison_mode" in result and "mode" not in result:
        result["mode"] = result.pop("period_comparison_mode")
    return result


def _slice_from_mapping(
    *,
    role: str,
    basis: Any,
    label: Any,
    explicit_slice: Any,
    mappings: Mapping[str, Any],
    options: Mapping[str, Any],
    time_window: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(explicit_slice, Mapping):
        _copy_present_keys(
            result,
            explicit_slice,
            (
                "label",
                "scenario",
                "period",
                "start_date",
                "end_date",
                "calendar",
                "calendar_type",
                "grain",
                "period_grain",
                "time_grain",
            ),
        )
        explicit_window = _normalize_time_window(explicit_slice.get("time_window"))
        if explicit_window:
            result["time_window"] = explicit_window
    if _is_present(label):
        result.setdefault("label", label)
        if basis == "scenario":
            result.setdefault("scenario", label)
        elif basis == "period":
            result.setdefault("period", label)
    scenario_key = f"{role}_scenario"
    period_key = f"{role}_period"
    for source in (mappings, options):
        if _is_present(source.get(scenario_key)):
            result["scenario"] = source[scenario_key]
        if _is_present(source.get(period_key)):
            result["period"] = source[period_key]
    side_window = time_window.get(role)
    if isinstance(side_window, Mapping):
        side_payload: dict[str, Any] = {}
        _copy_present_keys(
            side_payload,
            side_window,
            ("label", "start_date", "end_date", "period", "scenario"),
        )
        if side_payload:
            result["time_window"] = {
                **dict(result.get("time_window", {})),
                **side_payload,
            }
    start_key = f"{role}_start_date"
    end_key = f"{role}_end_date"
    side_window_payload = dict(result.get("time_window", {}))
    if _is_present(options.get(start_key)):
        side_window_payload["start_date"] = options[start_key]
    if _is_present(options.get(end_key)):
        side_window_payload["end_date"] = options[end_key]
    if side_window_payload:
        result["time_window"] = side_window_payload
    return result


def analysis_scope_from_recipe(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Return the normalized row/comparison scope used by chart artifacts.

    The scope is deterministic because these fields mechanically decide which
    rows, scenarios, and time windows a chart represents.
    """

    mappings = (
        recipe.get("mappings") if isinstance(recipe.get("mappings"), dict) else {}
    )
    options = recipe.get("options") if isinstance(recipe.get("options"), dict) else {}
    explicit_scope = recipe.get("analysis_scope") or options.get("analysis_scope")
    explicit = explicit_scope if isinstance(explicit_scope, Mapping) else {}

    scope: dict[str, Any] = {}
    filters = _filter_identity_from_recipe(recipe, options)
    if filters:
        scope["filters"] = filters

    period_axis: dict[str, Any] = {}
    _copy_present_keys(period_axis, mappings, ("period_column", "date_column"))
    _copy_present_keys(period_axis, options, ("scenario_column",))
    _copy_present_keys(period_axis, mappings, ("scenario_column",))
    if period_axis:
        scope["axis"] = period_axis

    selected_periods = _first_present(
        mappings, ("selected_periods", "period_values", "periods")
    )
    if selected_periods is None:
        selected_periods = _first_present(options, ("selected_periods", "periods"))
    if selected_periods is not None:
        scope["selected_periods"] = _as_list(selected_periods)

    time_window = _time_window_from_options(options)
    explicit_window = _normalize_time_window(explicit.get("time_window"))
    if explicit_window:
        time_window = {**time_window, **explicit_window}
    if time_window:
        scope["time_window"] = time_window

    basis = options.get("comparison_basis") or explicit.get("comparison_basis")
    mode = options.get("period_comparison_mode") or explicit.get(
        "period_comparison_mode"
    )
    baseline_label = mappings.get("baseline_period")
    comparison_label = mappings.get("comparison_period")
    if (
        _is_present(baseline_label)
        or _is_present(comparison_label)
        or _is_present(basis)
    ):
        comparison_scope: dict[str, Any] = {}
        if _is_present(basis):
            comparison_scope["basis"] = basis
        if _is_present(mode):
            comparison_scope["mode"] = mode
        baseline_slice = _slice_from_mapping(
            role="baseline",
            basis=basis,
            label=baseline_label,
            explicit_slice=explicit.get("baseline_slice"),
            mappings=mappings,
            options=options,
            time_window=time_window,
        )
        comparison_slice = _slice_from_mapping(
            role="comparison",
            basis=basis,
            label=comparison_label,
            explicit_slice=explicit.get("comparison_slice"),
            mappings=mappings,
            options=options,
            time_window=time_window,
        )
        if baseline_slice:
            comparison_scope["baseline"] = baseline_slice
        if comparison_slice:
            comparison_scope["comparison"] = comparison_slice
        if comparison_scope:
            scope["comparison"] = comparison_scope

    population_preparation = _population_preparation_identity_from_recipe(recipe)
    if population_preparation:
        scope["population_preparation"] = population_preparation

    return {
        key: json_safe(value)
        for key, value in scope.items()
        if value is not None and value != "" and value != [] and value != {}
    }


def _population_preparation_identity_from_recipe(
    recipe: Mapping[str, Any],
) -> dict[str, Any]:
    options = recipe.get("options") if isinstance(recipe.get("options"), dict) else {}
    # Prefer the effective contract written by deterministic preparation. Raw
    # request spellings are only used before a plugin has applied cohorts.
    for source in (options, recipe):
        if not isinstance(source, Mapping):
            continue
        for key in ("cohort_definition", "cohort_contract", "cohorts"):
            value = source.get(key)
            if value is not None and value != "" and value != [] and value != {}:
                return {key: value}

    population_preparation: dict[str, Any] = {}
    for source in (recipe, options):
        if not isinstance(source, Mapping):
            continue
        if source.get("derived_dimensions") not in (None, "", [], {}):
            population_preparation["derived_dimensions"] = source["derived_dimensions"]
        if source.get("like_for_like") not in (None, "", [], {}):
            population_preparation["like_for_like"] = source["like_for_like"]
    period_keys = (
        "cohort_current_period",
        "cohort_previous_period",
        "current_period_label",
        "previous_period_label",
    )
    periods = {
        key: options[key]
        for key in period_keys
        if key in options and options[key] not in (None, "", [], {})
    }
    if periods:
        population_preparation["periods"] = periods
    return population_preparation


def build_manifest_artifacts(
    artifact_paths: Iterable[str | Path],
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Build manifest artifact records from existing output paths."""

    records: list[dict[str, Any]] = []
    for artifact_path in artifact_paths:
        path = Path(artifact_path)
        if not path.exists() or not path.is_file():
            continue
        records.append(
            {
                "artifact_id": path.stem,
                "kind": artifact_kind(path),
                "path": relative_path(path, output_dir),
                "status": "written",
                "bytes": path.stat().st_size,
            }
        )
    return records


def frame_profile(frame: pl.DataFrame) -> dict[str, Any]:
    """Return row, column, and schema metadata for a prepared frame."""

    columns, schema = get_schema_and_column_names(frame)
    return {
        "row_count": get_row_count(frame),
        "column_count": frame.width,
        "columns": columns,
        "schema": {name: str(schema[name]) for name in columns},
    }


def write_prepared_data_manifest(
    *,
    output_dir: Path,
    plugin: str,
    chart_family: str,
    source_file: str | Path | None,
    prepared_path: Path,
    frame: pl.DataFrame,
    recipe: dict[str, Any],
    stage: str = "canonical",
    preparation_audit: dict[str, Any] | None = None,
) -> Path:
    """Write the shared prepared-data contract for one chart-family run.

    This is deterministic because it records mechanically verifiable metadata:
    the prepared file path, schema, row/column counts, mappings, options, and
    preparation audit. Business meaning remains with the reporting layer.
    """

    manifest_path = output_dir / "prepared_data_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "producer": {
                "plugin": plugin,
                "plugin_role": "chart_family_plugin",
                "chart_family": chart_family,
            },
            "source_file": str(source_file) if source_file is not None else None,
            "prepared_data": {
                "stage": stage,
                "path": relative_path(prepared_path, output_dir),
                **frame_profile(frame),
            },
            "mappings": recipe.get("mappings") or {},
            "options": recipe.get("options") or {},
            "preparation_audit": preparation_audit or {},
            "interpretation_boundary": {
                "prepared_data_is_model_source": True,
                "deterministic_scope": (
                    "file paths, schema, counts, mappings, options, and "
                    "preparation audit"
                ),
                "semantic_business_interpretation_owner": "reporting_consumer",
            },
        },
    )
    return manifest_path
