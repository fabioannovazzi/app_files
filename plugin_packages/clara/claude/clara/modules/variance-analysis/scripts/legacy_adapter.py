"""Adapter around the vendored legacy Mparanza variance runtime."""

from __future__ import annotations

import copy
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

__all__ = [
    "LegacyVariableBridgeAlternativeRun",
    "LegacyVariableBridgeSequence",
    "LegacyVariableBridgeRun",
    "LegacyVarianceRun",
    "cleanup_legacy_imports",
    "legacy_date_period_context",
    "run_legacy_variable_dimension_component_bridge",
    "run_legacy_variable_dimension_bridge",
    "run_legacy_variance",
]

TOTAL_DIMENSION = "__total"
BRIDGE_MEASURE_COLUMNS = {
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
AUTO_DRILLDOWN_MODES = {"none", "single_row", "dominant_row", "all_selected"}


@dataclass(frozen=True)
class LegacyVarianceRun:
    """Legacy runtime outputs normalized for the plugin contract."""

    frame: pl.DataFrame
    legacy_frame: pl.DataFrame
    audit: dict[str, Any]


@dataclass(frozen=True)
class LegacyVariableBridgeRun:
    """Legacy variable-dimension bridge outputs normalized for the plugin contract."""

    frame: pl.DataFrame
    legacy_frame: pl.DataFrame
    details_frame: pl.DataFrame
    snapshot_frame: pl.DataFrame
    candidate_frame: pl.DataFrame
    candidate_legacy_frame: pl.DataFrame
    drilldown_runs: dict[int, LegacyVariableBridgeSequence]
    moved_run: LegacyVariableBridgeSequence | None
    sweep_runs: dict[int, LegacyVariableBridgeAlternativeRun]
    param: dict[str, Any]
    chart: dict[str, Any]
    bridge_dimensions: list[str]
    audit: dict[str, Any]


@dataclass(frozen=True)
class LegacyVariableBridgeSequence:
    """One legacy ``process_node_combinations`` sequence and its side outputs."""

    frame: pl.DataFrame
    legacy_frame: pl.DataFrame
    details_frame: pl.DataFrame
    snapshot_frame: pl.DataFrame
    param: dict[str, Any]
    audit: dict[str, Any]


@dataclass(frozen=True)
class LegacyVariableBridgeAlternativeRun:
    """One alternative root-cause start row and optional drilldown outputs."""

    alternative_result: int
    sequence: LegacyVariableBridgeSequence
    drilldown_runs: dict[int, LegacyVariableBridgeSequence]
    moved_run: LegacyVariableBridgeSequence | None
    audit: dict[str, Any]


@dataclass(frozen=True)
class _LegacyVariableBridgeContext:
    """Prepared legacy bridge state reused across alternative starts."""

    imports: dict[str, Any]
    names: dict[str, str]
    config: dict[str, Any]
    report_dimensions: list[str]
    requested_calculation_grain: list[str]
    bridge_dimensions: list[str]
    param: dict[str, Any]
    chart: dict[str, Any]
    index_cols: list[str]
    candidate_frame: pl.DataFrame
    candidate_legacy_frame: pl.DataFrame


def _vendor_root() -> Path:
    """Return the plugin-local legacy module root."""

    return Path(__file__).resolve().parents[1] / "vendor"


def _shared_vendor_root() -> Path:
    """Return the repo shared legacy module root used during development."""

    return (
        Path(__file__).resolve().parents[3]
        / "plugins"
        / "_shared"
        / "variance"
        / "vendor"
    )


def _legacy_import_parent() -> Path:
    """Return shared plugin modules in dev, otherwise packaged vendor modules."""

    shared_root = _shared_vendor_root()
    if (shared_root / "modules" / "__init__.py").exists():
        return shared_root
    return _vendor_root()


def _uses_modules_from(module_root: Path) -> bool:
    """Return whether the currently loaded ``modules`` package uses ``module_root``."""

    module = sys.modules.get("modules")
    if module is None:
        return True
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        Path(module_file).resolve().relative_to(module_root.resolve())
    except ValueError:
        return False
    return True


def _ensure_legacy_import_path() -> Path:
    """Put shared/dev or vendored legacy tree first and avoid mixed imports."""

    legacy_parent = _legacy_import_parent()
    module_root = legacy_parent / "modules"
    if module_root.exists():
        legacy_text = str(legacy_parent)
        if legacy_text in sys.path:
            sys.path.remove(legacy_text)
        sys.path.insert(0, legacy_text)
        if not _uses_modules_from(module_root):
            for module_name in list(sys.modules):
                if module_name == "modules" or module_name.startswith("modules."):
                    del sys.modules[module_name]
    return legacy_parent


def _module_loaded_from_path(module_name: str, root: Path) -> bool:
    """Return whether ``module_name`` was loaded from ``root``."""

    module = sys.modules.get(module_name)
    if module is None:
        return False
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        Path(module_file).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def cleanup_legacy_imports() -> None:
    """Remove plugin-local legacy modules from global import state."""

    vendor_root = _vendor_root()
    shared_root = _shared_vendor_root()
    removable_roots = (vendor_root, shared_root)
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry not in {str(root) for root in removable_roots}
    ]
    for module_name in list(sys.modules):
        if module_name == "modules" or module_name.startswith("modules."):
            if any(
                _module_loaded_from_path(module_name, root) for root in removable_roots
            ):
                del sys.modules[module_name]


def _legacy_imports() -> dict[str, Any]:
    """Import legacy functions after the vendored path has priority."""

    vendor_root = _ensure_legacy_import_path()
    config = importlib.import_module("modules.utilities.config")
    helpers = importlib.import_module("modules.utilities.helpers")
    variance_utils = importlib.import_module("modules.variance.variance_utils")
    variance_formulas = importlib.import_module("modules.variance.variance_formulas")
    index_handling = importlib.import_module("modules.variance.index_handling")
    variance_orchestrator = importlib.import_module(
        "modules.variance.variance_orchestrator"
    )
    variance_decomposition = importlib.import_module(
        "modules.variance.variance_decomposition"
    )
    return {
        "vendor_root": vendor_root,
        "get_naming_params": config.get_naming_params,
        "get_config_params": config.get_config_params,
        "group_by_df_on_index_cols": helpers.group_by_df_on_index_cols,
        "calculate_unit_and_volume_price": helpers.calculate_unit_and_volume_price,
        "calculate_discount_per_units_and_volume": (
            helpers.calculate_discount_per_units_and_volume
        ),
        "calculate_cogs_per_units_and_volume": (
            helpers.calculate_cogs_per_units_and_volume
        ),
        "get_period_length_polars": helpers.get_period_length_polars,
        "get_rolling_and_year_to_date_period": (
            helpers.get_rolling_and_year_to_date_period
        ),
        "pivot_lazy_periods": helpers.pivot_lazy_periods,
        "rename_periods": variance_utils.rename_periods,
        "recalculate_price": variance_utils.recalculate_price,
        "set_parameters_on_scenario_option": (
            variance_utils.set_parameters_on_scenario_option
        ),
        "calculate_variance": variance_formulas.calculate_variance,
        "calculate_sales_mix_variance": variance_formulas.calculate_sales_mix_variance,
        "process_and_prepare_multidimensional_data": (
            index_handling.process_and_prepare_multidimensional_data
        ),
        "process_node_combinations": variance_decomposition.process_node_combinations,
        "process_variance_calculation": (
            variance_orchestrator.process_variance_calculation
        ),
    }


def legacy_date_period_context(
    df: pl.DataFrame,
    date_column: str,
) -> dict[str, Any]:
    """Return legacy most-recent-date and rolling/YTD labels for a date column."""

    imports = _legacy_imports()
    names = imports["get_naming_params"]()
    date_name = names["dateName"]
    lazy_dates = (
        df.select(pl.col(date_column).cast(pl.Date).alias(date_name))
        .drop_nulls(date_name)
        .lazy()
    )
    param: dict[str, Any] = {}
    chart: dict[str, Any] = {}
    param, most_recent_date, least_recent_date, period_length_months = imports[
        "get_period_length_polars"
    ](lazy_dates, param, True)
    rolling_symbol = names["rollingPeriodSymbol"]
    to_date_symbol = names["toDateSymbol"]
    return {
        "most_recent_date": most_recent_date,
        "least_recent_date": least_recent_date,
        "period_length_months": period_length_months,
        "rolling_label": imports["get_rolling_and_year_to_date_period"](
            rolling_symbol, param, chart, False
        ),
        "rolling_baseline_label": imports["get_rolling_and_year_to_date_period"](
            rolling_symbol, param, chart, True
        ),
        "ytd_label": imports["get_rolling_and_year_to_date_period"](
            to_date_symbol, param, chart, False
        ),
        "ytd_baseline_label": imports["get_rolling_and_year_to_date_period"](
            to_date_symbol, param, chart, True
        ),
    }


def _ordered_unique(values: list[str]) -> list[str]:
    """Return values once, preserving order."""

    return list(dict.fromkeys(values))


def _leaf_dimensions(recipe: dict[str, Any], report_dimensions: list[str]) -> list[str]:
    """Return the lowest grain used by the legacy bottom-up calculation."""

    mappings = recipe["mappings"]
    grain = list(mappings.get("calculation_grain") or report_dimensions)
    dimensions = _ordered_unique([*report_dimensions, *grain])
    return dimensions or [TOTAL_DIMENSION]


def _metric_aliases(
    mappings: dict[str, Any], names: dict[str, str]
) -> dict[str, str | None]:
    """Return plugin mapping fields as legacy metric aliases."""

    aliases: dict[str, str | None] = {
        "amount": names["monetaryLocalCurrencyName"],
        "units": names["unitsName"] if mappings.get("units_column") else None,
        "discount": names["discountName"] if mappings.get("discount_column") else None,
        "cogs": names["cogsName"] if mappings.get("cogs_column") else None,
        "net": names["netOfDiscountName"] if mappings.get("discount_column") else None,
        "margin": names["marginName"] if mappings.get("cogs_column") else None,
    }
    return aliases


def _numeric_expr(source: str, alias: str) -> pl.Expr:
    """Return a numeric column expression with legacy null handling."""

    return pl.col(source).cast(pl.Float64, strict=False).fill_null(0.0).alias(alias)


def _canonical_legacy_input(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    names: dict[str, str],
    leaf_dimensions: list[str],
) -> tuple[pl.DataFrame, list[str]]:
    """Convert user columns into legacy canonical column names."""

    mappings = recipe["mappings"]
    aliases = _metric_aliases(mappings, names)
    period_name = names["periodName"]
    expressions: list[pl.Expr] = []
    for dimension in leaf_dimensions:
        if dimension == TOTAL_DIMENSION:
            expressions.append(pl.lit("Total").alias(TOTAL_DIMENSION))
        else:
            expressions.append(
                pl.col(dimension).cast(pl.Utf8).fill_null("").alias(dimension)
            )
    expressions.extend(
        [
            pl.col(mappings["period_column"]).cast(pl.Utf8).alias(period_name),
            _numeric_expr(mappings["amount_column"], aliases["amount"] or "Sales"),
        ]
    )
    optional_metric_map = (
        ("units_column", aliases["units"]),
        ("discount_column", aliases["discount"]),
        ("cogs_column", aliases["cogs"]),
    )
    for mapping_key, alias in optional_metric_map:
        source = mappings.get(mapping_key)
        if source and alias:
            expressions.append(_numeric_expr(source, alias))
    working = df.select(expressions).filter(
        pl.col(period_name).is_in(
            [str(mappings["baseline_period"]), str(mappings["comparison_period"])]
        )
    )
    # The legacy bridge assigns row keys before ranking alternatives, so input
    # order must be explicit for reproducible alternativeResult behavior.
    working = working.sort([*leaf_dimensions, period_name])
    value_columns = [aliases["amount"] or "Sales"]
    if aliases["units"]:
        value_columns.append(aliases["units"])
    if aliases["discount"]:
        working = working.with_columns(
            (pl.col(aliases["amount"] or "Sales") - pl.col(aliases["discount"])).alias(
                aliases["net"] or "Sales Net Discount"
            )
        )
        value_columns.extend([aliases["discount"], aliases["net"]])
    if aliases["cogs"]:
        discount_expr = (
            pl.col(aliases["discount"]) if aliases["discount"] else pl.lit(0.0)
        )
        working = working.with_columns(
            (
                pl.col(aliases["amount"] or "Sales")
                - discount_expr
                - pl.col(aliases["cogs"])
            ).alias(aliases["margin"] or "Margin")
        )
        value_columns.extend([aliases["cogs"], aliases["margin"]])
    return working, _ordered_unique([column for column in value_columns if column])


def _legacy_param_and_chart(
    recipe: dict[str, Any],
    report_dimensions: list[str],
    names: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the small legacy state dictionaries required by old functions."""

    from modules.chart_harness import apply_legacy_filter_title_metadata

    mappings = recipe["mappings"]
    not_met = names["notMetConditionValue"]
    has_units = bool(mappings.get("units_column"))
    has_discount = bool(mappings.get("discount_column"))
    has_cogs = bool(mappings.get("cogs_column"))
    param = {
        names["numberOfPeriodsFound"]: 2,
        names["unitsColFound"]: has_units,
        names["volumeColFound"]: False,
        names["discountColFound"]: has_discount,
        names["cogsColFound"]: has_cogs,
        names["marginColFound"]: has_cogs,
        names["monetaryLocalCurrencyColFound"]: True,
        names["calculateDriverVariance"]: False,
        names["driverArray"]: [],
        names["isFilteredKey"]: not_met,
        names["selectedPeriods"]: [
            str(mappings["baseline_period"]),
            str(mappings["comparison_period"]),
        ],
        names["allPeriodsList"]: [
            str(mappings["baseline_period"]),
            str(mappings["comparison_period"]),
        ],
        names["impossibleToProcessFile"]: False,
        names["fileUploadDisabled"]: not_met,
        names["dropLowCorrelationCols"]: False,
        names["toTitleCase"]: False,
        names["reverseSortPeriods"]: False,
        names["isColumnMultiplied"]: False,
        names["renameTitlesDict"]: {},
    }
    variance_choice = (
        names["mixAndUnitsAggregation"]
        if has_units
        else names["totalVarianceAggregation"]
    )
    currency = str(recipe.get("options", {}).get("currency") or "EUR")
    chart = {
        names["selectedPeriods"]: [
            str(mappings["baseline_period"]),
            str(mappings["comparison_period"]),
        ],
        names["varianceAggregation"]: variance_choice,
        names["processingChoice"]: names["runOneDimensionalAnalysis"],
        names["mainDimension"]: report_dimensions,
        names["reverseSortPeriods"]: False,
        names["showInitialAndFinalValues"]: True,
        names["varianceInPercent"]: False,
        names["shareOfTotalMarket"]: False,
        names["plotSmallMultiplesWaterfall"]: False,
        names["filterDates"]: False,
        names["compareScenariosOrPeriods"]: names["comparePeriods"],
        names["chosenChart"]: names["verticalWaterfallChart"],
        names["varianceAnalysisChart"]: True,
        names["currencyChoice"]: currency,
        names["fullCurrencyName"]: currency,
    }
    chart = apply_legacy_filter_title_metadata(chart, names, recipe)
    return param, chart


def _column_or_zero(schema: dict[str, pl.DataType], column: str) -> pl.Expr:
    """Return a numeric column expression or zero when absent."""

    if column in schema:
        return pl.col(column).fill_null(0.0)
    return pl.lit(0.0)


def _column_or_null(schema: dict[str, pl.DataType], column: str) -> pl.Expr:
    """Return a column expression or null when absent."""

    if column in schema:
        return pl.col(column)
    return pl.lit(None)


def _safe_ratio(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    """Return a zero-denominator-safe ratio expression."""

    return pl.when(denominator == 0).then(0.0).otherwise(numerator / denominator)


def _collapse_legacy_rows(
    legacy_frame: pl.DataFrame | pl.LazyFrame,
    report_dimensions: list[str],
    param: dict[str, Any],
    recalculate_price: Any,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Collapse duplicate legacy rows after old mix processing."""

    schema = (
        legacy_frame.collect_schema()
        if isinstance(legacy_frame, pl.LazyFrame)
        else legacy_frame.schema
    )
    grouping_dimensions = report_dimensions or (
        [TOTAL_DIMENSION] if TOTAL_DIMENSION in schema else []
    )
    if not grouping_dimensions:
        return _collect_if_lazy(legacy_frame), param
    numeric_columns = [
        column
        for column, dtype in schema.items()
        if column not in grouping_dimensions and dtype.is_numeric()
    ]
    if not numeric_columns:
        return _collect_if_lazy(legacy_frame), param
    grouped = (
        legacy_frame.lazy()
        .group_by(grouping_dimensions)
        .agg([pl.col(column).sum().alias(column) for column in numeric_columns])
        .collect()
    )
    grouped, param = recalculate_price(grouped, param)
    if isinstance(grouped, pl.LazyFrame):
        grouped = grouped.collect()
    return grouped, param


def _merge_missing_legacy_columns(
    component_frame: pl.DataFrame,
    period_totals: pl.DataFrame,
    report_dimensions: list[str],
) -> pl.DataFrame:
    """Restore period-total columns that legacy mix output does not carry."""

    grouping_dimensions = report_dimensions or (
        [TOTAL_DIMENSION] if TOTAL_DIMENSION in component_frame.schema else []
    )
    if not grouping_dimensions:
        return component_frame
    missing_columns = [
        column
        for column in period_totals.columns
        if column not in component_frame.columns and column not in grouping_dimensions
    ]
    if not missing_columns:
        return component_frame
    return component_frame.join(
        period_totals.select([*grouping_dimensions, *missing_columns]),
        on=grouping_dimensions,
        how="left",
    )


def _normalize_legacy_output(
    legacy_frame: pl.DataFrame,
    report_dimensions: list[str],
    names: dict[str, str],
) -> pl.DataFrame:
    """Map legacy output columns to the plugin's stable result schema."""

    config = _legacy_imports()["get_config_params"]()
    periods = config["periodsArray"]
    separator = names["separatorString"]
    sales_p0 = names["monetaryLocalCurrencyName"] + separator + periods[0]
    sales_p1 = names["monetaryLocalCurrencyName"] + separator + periods[1]
    units_p0 = names["unitsName"] + separator + periods[0]
    units_p1 = names["unitsName"] + separator + periods[1]
    unit_price_p0 = names["pricePerUnitName"] + separator + periods[0]
    unit_price_p1 = names["pricePerUnitName"] + separator + periods[1]
    discount_p0 = names["discountName"] + separator + periods[0]
    discount_p1 = names["discountName"] + separator + periods[1]
    cogs_p0 = names["cogsName"] + separator + periods[0]
    cogs_p1 = names["cogsName"] + separator + periods[1]
    schema = legacy_frame.schema
    amount0 = _column_or_zero(schema, sales_p0)
    amount1 = _column_or_zero(schema, sales_p1)
    units0 = _column_or_zero(schema, units_p0)
    units1 = _column_or_zero(schema, units_p1)
    total_delta = _column_or_zero(schema, names["totalVariance"])
    price_variance = _column_or_zero(schema, names["priceVariance"])
    volume_source = (
        names["pureVolumeVarianceName"]
        if names["pureVolumeVarianceName"] in schema
        else names["volumeVariance"]
    )
    volume_variance = _column_or_zero(schema, volume_source)
    mix_variance = _column_or_zero(schema, names["mixVariance"])
    expressions: list[pl.Expr] = []
    for dimension in report_dimensions or [TOTAL_DIMENSION]:
        if dimension in schema:
            output_name = "segment" if dimension == TOTAL_DIMENSION else dimension
            expressions.append(pl.col(dimension).alias(output_name))
    expressions.extend(
        [
            amount0.alias("amount_baseline"),
            amount1.alias("amount_comparison"),
            (amount1 - amount0).alias("amount_delta"),
            total_delta.alias("total_delta"),
            pl.when(amount0 == 0)
            .then(None)
            .otherwise((amount1 - amount0) / amount0 * 100)
            .alias("amount_pct_change"),
            _column_or_null(schema, unit_price_p0).alias("price_baseline"),
            _column_or_null(schema, unit_price_p1).alias("price_comparison"),
            price_variance.alias("price_variance"),
            volume_variance.alias("volume_variance"),
            mix_variance.alias("mix_variance"),
            (total_delta - price_variance - volume_variance - mix_variance).alias(
                "component_reconciliation_delta"
            ),
        ]
    )
    if units_p0 in schema and units_p1 in schema:
        expressions.extend(
            [
                units0.alias("units_baseline"),
                units1.alias("units_comparison"),
                (units1 - units0).alias("units_delta"),
                _safe_ratio(amount0, units0).alias("calculated_price_baseline"),
                _safe_ratio(amount1, units1).alias("calculated_price_comparison"),
            ]
        )
    if discount_p0 in schema and discount_p1 in schema:
        discount0 = _column_or_zero(schema, discount_p0)
        discount1 = _column_or_zero(schema, discount_p1)
        net0 = amount0 - discount0
        net1 = amount1 - discount1
        expressions.extend(
            [
                discount0.alias("discount_baseline"),
                discount1.alias("discount_comparison"),
                (-(discount1 - discount0)).alias("discount_variance"),
                net0.alias("net_baseline"),
                net1.alias("net_comparison"),
                (net1 - net0).alias("net_delta"),
                pl.when(net0 == 0)
                .then(None)
                .otherwise((net1 - net0) / net0 * 100)
                .alias("net_pct_change"),
            ]
        )
    if cogs_p0 in schema and cogs_p1 in schema:
        cogs0 = _column_or_zero(schema, cogs_p0)
        cogs1 = _column_or_zero(schema, cogs_p1)
        discount0 = _column_or_zero(schema, discount_p0)
        discount1 = _column_or_zero(schema, discount_p1)
        margin0 = amount0 - discount0 - cogs0
        margin1 = amount1 - discount1 - cogs1
        expressions.extend(
            [
                cogs0.alias("cogs_baseline"),
                cogs1.alias("cogs_comparison"),
                (cogs1 - cogs0).alias("cogs_delta"),
                (-(cogs1 - cogs0)).alias("cogs_variance"),
                margin0.alias("margin_baseline"),
                margin1.alias("margin_comparison"),
                (margin1 - margin0).alias("margin_delta"),
                pl.when(margin0 == 0)
                .then(None)
                .otherwise((margin1 - margin0) / margin0 * 100)
                .alias("margin_pct_change"),
                pl.lit(0.0).alias("margin_component_reconciliation_delta"),
            ]
        )
    return legacy_frame.select(expressions).sort("total_delta", descending=True)


def _collect_if_lazy(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Collect a lazy frame while preserving eager frames."""

    if isinstance(frame, pl.LazyFrame):
        return frame.collect()
    return frame


def _add_variable_bridge_defaults(
    param: dict[str, Any],
    canonical: pl.DataFrame,
    dimensions: list[str],
    names: dict[str, str],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Populate legacy bridge metadata normally produced by UI intake."""

    if dimensions:
        counts = canonical.select(
            [pl.col(dimension).n_unique().alias(dimension) for dimension in dimensions]
        ).to_dicts()[0]
    else:
        counts = {}
    param[names["uniqueValuesInColumnDict"]] = {
        dimension: int(counts[dimension]) for dimension in dimensions
    }
    param[names["uniqueValuesInColumnList"]] = list(dimensions)
    param[names["maxIndexArrayLength"]] = min(
        len(dimensions),
        config[names["maxIndexArrayLength"]],
    )
    return param


def _active_bridge_dimensions(row: dict[str, Any]) -> str:
    """Return the comma-separated dimensions active in a legacy bridge row."""

    inactive = {"", "All", "N/A", "None", "null"}
    active = [
        dimension
        for dimension, value in row.items()
        if value is not None and str(value) not in inactive
    ]
    return ",".join(active) if active else "total"


def _normalize_legacy_bridge_output(
    legacy_frame: pl.DataFrame,
    dimensions: list[str],
    names: dict[str, str],
    *,
    sort_by_variance: bool = True,
) -> pl.DataFrame:
    """Map legacy variable-dimension bridge rows to a stable plugin schema."""

    if legacy_frame.is_empty():
        return legacy_frame
    config = _legacy_imports()["get_config_params"]()
    periods = config["periodsArray"]
    separator = names["separatorString"]
    sales_p0 = names["monetaryLocalCurrencyName"] + separator + periods[0]
    sales_p1 = names["monetaryLocalCurrencyName"] + separator + periods[1]
    units_p0 = names["unitsName"] + separator + periods[0]
    units_p1 = names["unitsName"] + separator + periods[1]
    variance_type = names["varianceTypeName"]
    variance_amount = names["varianceAmountName"]
    number_of_nodes = names["numberOfNodes"]
    unique_values = names["uniqueValuesInCombination"]
    schema = legacy_frame.schema
    present_dimensions = [dimension for dimension in dimensions if dimension in schema]
    expressions: list[pl.Expr] = [
        pl.col(dimension).cast(pl.Utf8).fill_null("All").alias(dimension)
        for dimension in present_dimensions
    ]
    if number_of_nodes in schema:
        expressions.append(
            pl.col(number_of_nodes)
            .cast(pl.Int64, strict=False)
            .fill_null(0)
            .alias("bridge_level")
        )
    if present_dimensions:
        expressions.append(
            pl.struct(present_dimensions)
            .map_elements(_active_bridge_dimensions, return_dtype=pl.Utf8)
            .alias("bridge_dimensions")
        )
    else:
        expressions.append(pl.lit("total").alias("bridge_dimensions"))
    if variance_type in schema:
        expressions.append(pl.col(variance_type).cast(pl.Utf8).alias("variance_type"))
    if variance_amount in schema:
        expressions.append(
            pl.col(variance_amount)
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("variance_amount")
        )
    for legacy_column, output_column in (
        (sales_p0, "amount_baseline"),
        (sales_p1, "amount_comparison"),
        (units_p0, "units_baseline"),
        (units_p1, "units_comparison"),
        (unique_values, "bridge_unique_value_weight"),
    ):
        if legacy_column in schema:
            expressions.append(pl.col(legacy_column).alias(output_column))
    normalized = legacy_frame.select(expressions)
    if "bridge_level" not in normalized.schema:
        normalized = normalized.with_columns(
            pl.col("bridge_dimensions").str.split(",").list.len().alias("bridge_level")
        )
    if sort_by_variance and "variance_amount" in normalized.schema:
        tie_breakers = [
            column
            for column in [*present_dimensions, "variance_type", "bridge_dimensions"]
            if column in normalized.schema
        ]
        normalized = normalized.sort(
            ["variance_amount", *tie_breakers],
            descending=[True, *[False for _column in tie_breakers]],
        )
    return normalized


def _bridge_dimension_audit(
    normalized: pl.DataFrame,
    report_dimensions: list[str],
    requested_calculation_grain: list[str],
    effective_bridge_dimensions: list[str],
) -> dict[str, list[str]]:
    """Return requested, emitted, dropped, and added bridge dimension metadata."""

    emitted_dimensions = [
        column for column in normalized.columns if column not in BRIDGE_MEASURE_COLUMNS
    ]
    dropped_dimensions = [
        dimension
        for dimension in effective_bridge_dimensions
        if dimension not in emitted_dimensions
    ]
    internally_added_dimensions = [
        dimension
        for dimension in emitted_dimensions
        if dimension not in effective_bridge_dimensions
    ]
    dropped_report_dimensions = [
        dimension
        for dimension in report_dimensions
        if dimension not in emitted_dimensions
    ]
    return {
        "requested_report_dimensions": report_dimensions,
        "requested_calculation_grain": requested_calculation_grain,
        "effective_bridge_dimensions": effective_bridge_dimensions,
        "emitted_bridge_dimensions": emitted_dimensions,
        "dropped_bridge_dimensions": dropped_dimensions,
        "internally_added_bridge_dimensions": internally_added_dimensions,
        "dropped_report_dimensions": dropped_report_dimensions,
    }


def _legacy_sequence_audit(
    *,
    run_name: str,
    frame: pl.DataFrame,
    details_frame: pl.DataFrame,
    snapshot_frame: pl.DataFrame,
    param: dict[str, Any],
    names: dict[str, str],
) -> dict[str, Any]:
    """Return audit metadata for one legacy sequence run."""

    selected_dimensions: list[str] = []
    if not frame.is_empty() and "bridge_dimensions" in frame.schema:
        selected_dimensions = frame["bridge_dimensions"].to_list()
    unique_selected_dimensions = list(dict.fromkeys(selected_dimensions))
    return {
        "legacy_sequence_run": run_name,
        "row_count": frame.height,
        "sequence_row_count": frame.height,
        "selected_sequence_bridge_dimensions": selected_dimensions,
        "selected_sequence_unique_bridge_dimensions": unique_selected_dimensions,
        "selected_sequence_has_mixed_dimensions": len(unique_selected_dimensions) > 1,
        "details_row_count": details_frame.height,
        "snapshot_row_count": snapshot_frame.height,
        "sequence_running_total": param.get(names["runningTotalName"]),
        "sequence_rows_until_stop": param.get(names["rowResultsUntilStop"]),
    }


def _run_legacy_bridge_sequence(
    imports: dict[str, Any],
    source_frame: pl.DataFrame,
    index_cols: list[str],
    param: dict[str, Any],
    chart: dict[str, Any],
    run_name: str,
    bridge_dimensions: list[str],
    names: dict[str, str],
    *,
    sort_by_variance: bool = False,
) -> LegacyVariableBridgeSequence:
    """Run legacy ``process_node_combinations`` and normalize all outputs."""

    sequence_param = copy.deepcopy(param)
    sequence_frame, details_frame, snapshot_frame, sequence_param = imports[
        "process_node_combinations"
    ](
        source_frame,
        index_cols,
        sequence_param,
        copy.deepcopy(chart),
        run_name,
    )
    sequence_legacy_frame = _collect_if_lazy(sequence_frame)
    collected_details = _collect_if_lazy(details_frame)
    collected_snapshot = _collect_if_lazy(snapshot_frame)
    normalized = _normalize_legacy_bridge_output(
        sequence_legacy_frame,
        bridge_dimensions,
        names,
        sort_by_variance=sort_by_variance,
    )
    return LegacyVariableBridgeSequence(
        frame=normalized,
        legacy_frame=sequence_legacy_frame,
        details_frame=collected_details,
        snapshot_frame=collected_snapshot,
        param=sequence_param,
        audit=_legacy_sequence_audit(
            run_name=run_name,
            frame=normalized,
            details_frame=collected_details,
            snapshot_frame=collected_snapshot,
            param=sequence_param,
            names=names,
        ),
    )


def _root_cause_option_rows(options: dict[str, Any], key: str) -> list[int]:
    """Return normalized positive row numbers from root-cause options."""

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


def _root_cause_move_rows(options: dict[str, Any]) -> dict[int, list[int]]:
    """Return normalized move-row mappings from root-cause options."""

    raw_value = options.get("root_cause_bridge_move_rows", {})
    if not isinstance(raw_value, dict):
        return {}
    result: dict[int, list[int]] = {}
    for main_row, drilldown_rows in raw_value.items():
        try:
            parsed_main = int(main_row)
        except (TypeError, ValueError):
            continue
        if parsed_main <= 0:
            continue
        rows = drilldown_rows if isinstance(drilldown_rows, list) else [drilldown_rows]
        parsed_rows: list[int] = []
        for row in rows:
            try:
                parsed_row = int(row)
            except (TypeError, ValueError):
                continue
            if parsed_row > 0 and parsed_row not in parsed_rows:
                parsed_rows.append(parsed_row)
        if parsed_rows:
            result[parsed_main] = parsed_rows
    return result


def _requested_drilldown_rows(
    *,
    selected_row_count: int,
    options: dict[str, Any],
    move_rows: dict[int, list[int]],
) -> tuple[list[int], list[int]]:
    """Return valid and invalid requested main rows for drilldown processing."""

    rows = (
        list(range(1, selected_row_count + 1))
        if bool(options.get("root_cause_bridge_drilldown_all", False))
        else _root_cause_option_rows(options, "root_cause_bridge_drilldown_rows")
    )
    for main_row in move_rows:
        if main_row not in rows:
            rows.append(main_row)
    valid = [row for row in rows if 1 <= row <= selected_row_count]
    invalid = [row for row in rows if row < 1 or row > selected_row_count]
    return valid, invalid


def _details_for_main_row(
    details_frame: pl.DataFrame,
    main_legacy_frame: pl.DataFrame,
    main_row: int,
    names: dict[str, str],
) -> pl.DataFrame:
    """Return the legacy detail rows for a 1-based main sequence row."""

    drilldown_key = names["drilldownKey"]
    random_key = names["randomKey"]
    if (
        details_frame.is_empty()
        or main_legacy_frame.is_empty()
        or main_row < 1
        or main_row > main_legacy_frame.height
        or drilldown_key not in details_frame.schema
        or random_key not in main_legacy_frame.schema
    ):
        return pl.DataFrame()
    row_key = main_legacy_frame[main_row - 1, random_key]
    if row_key is None:
        return pl.DataFrame()
    return details_frame.filter(pl.col(drilldown_key) == row_key)


def _bridge_row_filter_dict(
    row: dict[str, Any],
    bridge_dimensions: list[str],
    names: dict[str, str],
) -> dict[str, Any]:
    """Return a legacy filter dict for a selected bridge row."""

    nan_value = names["nanFillValue"]
    filter_dict: dict[str, Any] = {}
    for dimension in bridge_dimensions:
        value = row.get(dimension)
        if value is None:
            continue
        text_value = str(value)
        if text_value and text_value != nan_value:
            filter_dict[dimension] = value
    variance_type = row.get("variance_type")
    if variance_type is not None and str(variance_type):
        filter_dict[names["varianceTypeName"]] = variance_type
    return filter_dict


def _next_insert_slot(insert_dict: dict[int, dict[str, Any]], start_slot: int) -> int:
    """Return the next available legacy insertion slot."""

    slot = start_slot
    while slot in insert_dict:
        slot += 1
    return slot


def _build_insert_at_row_dict(
    *,
    move_rows: dict[int, list[int]],
    drilldown_runs: dict[int, LegacyVariableBridgeSequence],
    bridge_dimensions: list[str],
    names: dict[str, str],
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """Build legacy ``insertAtRowDict`` from selected drilldown rows."""

    insert_dict: dict[int, dict[str, Any]] = {}
    invalid: dict[str, list[int]] = {}
    inserted: dict[str, list[int]] = {}
    slot_map: dict[str, list[int]] = {}
    for main_row, drilldown_rows in sorted(move_rows.items()):
        drilldown_run = drilldown_runs.get(main_row)
        if drilldown_run is None or drilldown_run.frame.is_empty():
            invalid[str(main_row)] = drilldown_rows
            continue
        drilldown_dicts = drilldown_run.frame.to_dicts()
        for drilldown_row in drilldown_rows:
            if drilldown_row < 1 or drilldown_row > len(drilldown_dicts):
                invalid.setdefault(str(main_row), []).append(drilldown_row)
                continue
            filter_dict = _bridge_row_filter_dict(
                drilldown_dicts[drilldown_row - 1],
                bridge_dimensions,
                names,
            )
            if not filter_dict:
                invalid.setdefault(str(main_row), []).append(drilldown_row)
                continue
            slot = _next_insert_slot(insert_dict, main_row - 1)
            insert_dict[slot] = filter_dict
            inserted.setdefault(str(main_row), []).append(drilldown_row)
            slot_map.setdefault(str(main_row), []).append(slot)
    return insert_dict, {
        "inserted": inserted,
        "invalid": invalid,
        "insert_slots": slot_map,
    }


def _bounded_positive_int(value: Any, default: int, *, maximum: int) -> int:
    """Return a positive integer clamped to ``maximum``."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed <= 0:
        parsed = default
    return min(parsed, maximum)


def _root_cause_sweep_values(options: dict[str, Any]) -> list[int]:
    """Return requested alternativeResult values for an automatic sweep."""

    if not bool(options.get("root_cause_bridge_alternative_sweep", False)):
        return []
    start = _bounded_positive_int(
        options.get("root_cause_bridge_alternative_sweep_start"), 1, maximum=10
    )
    end = _bounded_positive_int(
        options.get("root_cause_bridge_alternative_sweep_end"), 10, maximum=10
    )
    if end < start:
        start, end = end, start
    return list(range(start, end + 1))


def _root_cause_auto_drilldown_mode(options: dict[str, Any]) -> str:
    """Return the normalized automatic drilldown mode."""

    raw_value = str(options.get("root_cause_bridge_auto_drilldown") or "none")
    mode = raw_value.strip().lower().replace("-", "_")
    return mode if mode in AUTO_DRILLDOWN_MODES else "none"


def _root_cause_auto_drilldown_min_share(options: dict[str, Any]) -> float:
    """Return the minimum absolute-variance share for dominant-row drilldown."""

    try:
        value = float(options.get("root_cause_bridge_auto_drilldown_min_share", 0.75))
    except (TypeError, ValueError):
        value = 0.75
    return min(max(value, 0.0), 1.0)


def _valid_requested_rows(
    *,
    selected_row_count: int,
    rows: list[int],
) -> tuple[list[int], list[int]]:
    """Return valid and invalid 1-based selected sequence rows."""

    valid: list[int] = []
    invalid: list[int] = []
    for row in rows:
        if 1 <= row <= selected_row_count:
            if row not in valid:
                valid.append(row)
        else:
            invalid.append(row)
    return valid, invalid


def _auto_drilldown_rows(
    sequence: LegacyVariableBridgeSequence,
    mode: str,
    *,
    min_share: float,
) -> list[int]:
    """Choose selected main rows for automatic legacy drilldown."""

    frame = sequence.frame
    if mode == "none" or frame.is_empty():
        return []
    if mode == "single_row":
        return [1] if frame.height == 1 else []
    if mode == "all_selected":
        return list(range(1, frame.height + 1))
    if mode != "dominant_row" or "variance_amount" not in frame.schema:
        return []
    ranked = frame.with_row_index("__row_number").with_columns(
        pl.col("variance_amount").abs().alias("__abs_variance")
    )
    total_abs = ranked.select(pl.col("__abs_variance").sum()).item()
    if total_abs is None or float(total_abs) <= 0:
        return []
    top_row = ranked.sort("__abs_variance", descending=True).row(0, named=True)
    share = float(top_row["__abs_variance"]) / float(total_abs)
    if share < min_share:
        return []
    return [int(top_row["__row_number"]) + 1]


def _run_drilldown_sequences(
    context: _LegacyVariableBridgeContext,
    main_sequence: LegacyVariableBridgeSequence,
    requested_rows: list[int],
) -> tuple[dict[int, LegacyVariableBridgeSequence], str, dict[str, str]]:
    """Run legacy drilldowns for selected main sequence rows."""

    names = context.names
    if not requested_rows:
        return {}, "not_requested", {}
    if main_sequence.details_frame.is_empty():
        return {}, "not_written_details_empty", {}
    drilldown_runs: dict[int, LegacyVariableBridgeSequence] = {}
    drilldown_row_status: dict[str, str] = {}
    drilldown_status = "not_written_no_rows"
    for main_row in requested_rows:
        detail_frame = _details_for_main_row(
            main_sequence.details_frame,
            main_sequence.legacy_frame,
            main_row,
            names,
        )
        if detail_frame.is_empty():
            drilldown_row_status[str(main_row)] = "not_written_no_detail_rows"
            continue
        drilldown_param = copy.deepcopy(context.param)
        drilldown_param[names["alternativeResult"]] = 1
        drilldown_run = _run_legacy_bridge_sequence(
            context.imports,
            detail_frame,
            context.index_cols,
            drilldown_param,
            context.chart,
            names["drilldownReportRunName"],
            context.bridge_dimensions,
            names,
        )
        drilldown_runs[main_row] = drilldown_run
        drilldown_row_status[str(main_row)] = (
            "written" if not drilldown_run.frame.is_empty() else "not_written_empty"
        )
    if drilldown_runs:
        drilldown_status = "written"
    return drilldown_runs, drilldown_status, drilldown_row_status


def _run_prepared_variable_bridge_alternative(
    context: _LegacyVariableBridgeContext,
    *,
    options: dict[str, Any],
    alternative_result: int,
    move_rows: dict[int, list[int]],
    manual_drilldown_rows: list[int] | None = None,
    drilldown_all: bool | None = None,
    auto_drilldown_mode: str = "none",
) -> LegacyVariableBridgeAlternativeRun:
    """Run one alternativeResult against a prepared legacy candidate universe."""

    names = context.names
    alternative_result = _bounded_positive_int(alternative_result, 1, maximum=10)
    param = copy.deepcopy(context.param)
    param[names["alternativeResult"]] = alternative_result
    main_sequence = _run_legacy_bridge_sequence(
        context.imports,
        context.candidate_legacy_frame,
        context.index_cols,
        param,
        context.chart,
        names["mainReportRunName"],
        context.bridge_dimensions,
        names,
    )
    if drilldown_all is None:
        drilldown_all = bool(options.get("root_cause_bridge_drilldown_all", False))
    if manual_drilldown_rows is None:
        requested_drilldown_rows, invalid_drilldown_rows = _requested_drilldown_rows(
            selected_row_count=main_sequence.frame.height,
            options=options,
            move_rows=move_rows,
        )
    else:
        requested_drilldown_rows, invalid_drilldown_rows = _valid_requested_rows(
            selected_row_count=main_sequence.frame.height,
            rows=manual_drilldown_rows,
        )
        for main_row in move_rows:
            if main_row not in requested_drilldown_rows:
                requested_drilldown_rows.append(main_row)
        requested_drilldown_rows, invalid_from_move_rows = _valid_requested_rows(
            selected_row_count=main_sequence.frame.height,
            rows=requested_drilldown_rows,
        )
        invalid_drilldown_rows.extend(invalid_from_move_rows)
    if drilldown_all:
        requested_drilldown_rows = list(range(1, main_sequence.frame.height + 1))
        invalid_drilldown_rows = []
    auto_rows = _auto_drilldown_rows(
        main_sequence,
        auto_drilldown_mode,
        min_share=_root_cause_auto_drilldown_min_share(options),
    )
    for row in auto_rows:
        if row not in requested_drilldown_rows:
            requested_drilldown_rows.append(row)
    drilldown_runs, drilldown_status, drilldown_row_status = _run_drilldown_sequences(
        context,
        main_sequence,
        requested_drilldown_rows,
    )
    insert_at_row_dict, move_rows_audit = _build_insert_at_row_dict(
        move_rows=move_rows,
        drilldown_runs=drilldown_runs,
        bridge_dimensions=context.bridge_dimensions,
        names=names,
    )
    moved_run: LegacyVariableBridgeSequence | None = None
    if insert_at_row_dict:
        moved_param = copy.deepcopy(context.param)
        moved_param[names["alternativeResult"]] = alternative_result
        moved_param[names["insertAtRowDict"]] = insert_at_row_dict
        moved_run = _run_legacy_bridge_sequence(
            context.imports,
            context.candidate_legacy_frame,
            context.index_cols,
            moved_param,
            context.chart,
            names["moveRowReportRunName"],
            context.bridge_dimensions,
            names,
        )
        moved_rows_status = "written" if not moved_run.frame.is_empty() else "empty"
    elif move_rows:
        moved_rows_status = "not_written_no_insert_rows"
    else:
        moved_rows_status = "not_requested"
    audit = {
        "alternative_result": alternative_result,
        "legacy_sequence_run": names["mainReportRunName"],
        "row_count": main_sequence.frame.height,
        "sequence_row_count": main_sequence.frame.height,
        "selected_sequence_bridge_dimensions": main_sequence.audit[
            "selected_sequence_bridge_dimensions"
        ],
        "selected_sequence_unique_bridge_dimensions": main_sequence.audit[
            "selected_sequence_unique_bridge_dimensions"
        ],
        "selected_sequence_has_mixed_dimensions": main_sequence.audit[
            "selected_sequence_has_mixed_dimensions"
        ],
        "details_row_count": main_sequence.details_frame.height,
        "snapshot_row_count": main_sequence.snapshot_frame.height,
        "sequence_running_total": main_sequence.param.get(names["runningTotalName"]),
        "sequence_rows_until_stop": main_sequence.param.get(
            names["rowResultsUntilStop"]
        ),
        "drilldown_requested_rows": requested_drilldown_rows,
        "drilldown_invalid_rows": invalid_drilldown_rows,
        "drilldown_all": drilldown_all,
        "automatic_drilldown_mode": auto_drilldown_mode,
        "automatic_drilldown_rows": auto_rows,
        "drilldown_status": drilldown_status,
        "drilldown_row_status": drilldown_row_status,
        "drilldown_row_counts": {
            str(row): run.frame.height for row, run in drilldown_runs.items()
        },
        "moved_rows_requested": {
            str(row): selected for row, selected in sorted(move_rows.items())
        },
        "moved_rows_status": moved_rows_status,
        "moved_rows_insert_at_row_dict": insert_at_row_dict,
        "moved_rows_insert_audit": move_rows_audit,
        "moved_rows_row_count": moved_run.frame.height if moved_run else 0,
    }
    return LegacyVariableBridgeAlternativeRun(
        alternative_result=alternative_result,
        sequence=main_sequence,
        drilldown_runs=drilldown_runs,
        moved_run=moved_run,
        audit=audit,
    )


def _prepare_legacy_variable_bridge_context(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    variance_mode: str = "total_variance",
) -> _LegacyVariableBridgeContext:
    """Build the candidate universe once for root-cause alternatives."""

    imports = _legacy_imports()
    names = imports["get_naming_params"]()
    config = imports["get_config_params"]()
    report_dimensions = list(recipe["mappings"].get("dimensions") or [])
    requested_calculation_grain = list(
        recipe["mappings"].get("calculation_grain") or []
    )
    bridge_dimensions = _leaf_dimensions(recipe, report_dimensions)
    param, chart = _legacy_param_and_chart(recipe, bridge_dimensions, names)
    chart[names["processingChoice"]] = names["runVariableDimensionalAnalysis"]
    if variance_mode == "component_variance":
        chart[names["varianceAggregation"]] = names["mixAndUnitsAggregation"]
        chart[names["showInitialAndFinalValues"]] = False
    else:
        chart[names["varianceAggregation"]] = names["totalVarianceAggregation"]
        chart[names["showInitialAndFinalValues"]] = True
    chart[names["mainDimension"]] = bridge_dimensions
    param[names["parameterSetting"]] = names["largestCombinationOption"]
    param = imports["set_parameters_on_scenario_option"](param)
    param[names["aggregationChoice"]] = config[names["aggregationChoiceArray"]][0]
    canonical, value_columns = _canonical_legacy_input(
        df, recipe, names, bridge_dimensions
    )
    param = _add_variable_bridge_defaults(
        param,
        canonical,
        bridge_dimensions,
        names,
        config,
    )
    period_name = names["periodName"]
    index_columns = [*bridge_dimensions, period_name]
    empty_lazy = pl.DataFrame().lazy()
    df_dict, index_cols, _original_value_cols, param, chart = imports[
        "process_and_prepare_multidimensional_data"
    ](
        param,
        {},
        canonical.lazy(),
        empty_lazy,
        canonical.lazy(),
        canonical.lazy(),
        empty_lazy,
        index_columns,
        value_columns,
        chart,
        [],
        value_columns.copy(),
        {},
        {},
        {},
        {},
        False,
    )
    candidate_legacy_frame = _collect_if_lazy(
        df_dict.get(names["dfName"], pl.DataFrame())
    )
    candidate_normalized = _normalize_legacy_bridge_output(
        candidate_legacy_frame,
        bridge_dimensions,
        names,
    )
    return _LegacyVariableBridgeContext(
        imports=imports,
        names=names,
        config=config,
        report_dimensions=report_dimensions,
        requested_calculation_grain=requested_calculation_grain,
        bridge_dimensions=bridge_dimensions,
        param=param,
        chart=chart,
        index_cols=index_cols,
        candidate_frame=candidate_normalized,
        candidate_legacy_frame=candidate_legacy_frame,
    )


def run_legacy_variable_dimension_bridge(
    df: pl.DataFrame,
    recipe: dict[str, Any],
) -> LegacyVariableBridgeRun:
    """Run the legacy variable-dimension bridge calculation."""

    report_dimensions = list(recipe["mappings"].get("dimensions") or [])
    requested_calculation_grain = list(
        recipe["mappings"].get("calculation_grain") or []
    )
    bridge_dimensions = _leaf_dimensions(recipe, report_dimensions)
    if len(bridge_dimensions) < 2:
        empty = pl.DataFrame()
        return LegacyVariableBridgeRun(
            frame=empty,
            legacy_frame=empty,
            details_frame=empty,
            snapshot_frame=empty,
            candidate_frame=empty,
            candidate_legacy_frame=empty,
            drilldown_runs={},
            moved_run=None,
            sweep_runs={},
            param={},
            chart={},
            bridge_dimensions=bridge_dimensions,
            audit={
                "enabled": False,
                "reason": "requires at least two dimensions",
                "report_dimensions": report_dimensions,
                "calculation_grain": bridge_dimensions,
                **_bridge_dimension_audit(
                    empty,
                    report_dimensions,
                    requested_calculation_grain,
                    bridge_dimensions,
                ),
            },
        )
    options = recipe.get("options") or {}
    alternative_result = _bounded_positive_int(
        options.get("root_cause_bridge_alternative_result"), 1, maximum=10
    )
    context = _prepare_legacy_variable_bridge_context(
        df,
        recipe,
        variance_mode="total_variance",
    )
    names = context.names
    move_rows = _root_cause_move_rows(options)
    main_run = _run_prepared_variable_bridge_alternative(
        context,
        options=options,
        alternative_result=alternative_result,
        move_rows=move_rows,
    )
    sweep_values = _root_cause_sweep_values(options)
    auto_drilldown_mode = _root_cause_auto_drilldown_mode(options)
    sweep_runs: dict[int, LegacyVariableBridgeAlternativeRun] = {}
    for sweep_alternative in sweep_values:
        sweep_runs[sweep_alternative] = _run_prepared_variable_bridge_alternative(
            context,
            options=options,
            alternative_result=sweep_alternative,
            move_rows={},
            manual_drilldown_rows=[],
            drilldown_all=False,
            auto_drilldown_mode=auto_drilldown_mode,
        )
    dimension_audit = _bridge_dimension_audit(
        context.candidate_frame,
        context.report_dimensions,
        context.requested_calculation_grain,
        context.bridge_dimensions,
    )
    audit = {
        "enabled": True,
        "vendor_root": str(context.imports["vendor_root"]),
        "variable_bridge_source": (
            "modules.variance.index_handling."
            "process_and_prepare_multidimensional_data"
        ),
        "variable_bridge_combination": (
            "modules.variance.variance_orchestrator.output_df_with_combinations"
        ),
        "variable_bridge_subtraction": (
            "modules.variance.variance_orchestrator."
            "delete_duplicate_nodes_and_melt_result"
        ),
        "variable_bridge_filter": (
            "modules.variance.variance_utils.filter_by_number_of_nodes"
        ),
        "variable_bridge_sequence": (
            "modules.variance.variance_decomposition.process_node_combinations"
        ),
        "variable_bridge_drilldown_sequence": (
            "modules.variance.variance_decomposition.process_node_combinations"
        ),
        "variable_bridge_move_rows": (
            "modules.variance.variance_decomposition.insert_drilldown_row_in_main_report"
        ),
        "legacy_processing_choice": names["runVariableDimensionalAnalysis"],
        "legacy_variance_aggregation": context.chart[names["varianceAggregation"]],
        "root_cause_variance_mode": "total_variance",
        "plugin_variance_aggregation": "total_variance",
        "legacy_sequence_run": names["mainReportRunName"],
        "report_dimensions": report_dimensions,
        "calculation_grain": bridge_dimensions,
        **dimension_audit,
        "legacy_periods": context.config["periodsArray"],
        "alternative_result": alternative_result,
        "candidate_row_count": context.candidate_frame.height,
        "row_count": main_run.sequence.frame.height,
        "sequence_row_count": main_run.sequence.frame.height,
        "selected_sequence_bridge_dimensions": main_run.sequence.audit[
            "selected_sequence_bridge_dimensions"
        ],
        "selected_sequence_unique_bridge_dimensions": main_run.sequence.audit[
            "selected_sequence_unique_bridge_dimensions"
        ],
        "selected_sequence_has_mixed_dimensions": main_run.sequence.audit[
            "selected_sequence_has_mixed_dimensions"
        ],
        "details_row_count": main_run.sequence.details_frame.height,
        "snapshot_row_count": main_run.sequence.snapshot_frame.height,
        "sequence_running_total": main_run.sequence.param.get(
            names["runningTotalName"]
        ),
        "sequence_rows_until_stop": main_run.sequence.param.get(
            names["rowResultsUntilStop"]
        ),
        "drilldown_requested_rows": main_run.audit["drilldown_requested_rows"],
        "drilldown_invalid_rows": main_run.audit["drilldown_invalid_rows"],
        "drilldown_all": main_run.audit["drilldown_all"],
        "drilldown_status": main_run.audit["drilldown_status"],
        "drilldown_row_status": main_run.audit["drilldown_row_status"],
        "drilldown_row_counts": main_run.audit["drilldown_row_counts"],
        "moved_rows_requested": main_run.audit["moved_rows_requested"],
        "moved_rows_status": main_run.audit["moved_rows_status"],
        "moved_rows_insert_at_row_dict": main_run.audit[
            "moved_rows_insert_at_row_dict"
        ],
        "moved_rows_insert_audit": main_run.audit["moved_rows_insert_audit"],
        "moved_rows_row_count": main_run.audit["moved_rows_row_count"],
        "alternative_sweep_enabled": bool(sweep_values),
        "alternative_sweep_values": sweep_values,
        "alternative_sweep_auto_drilldown": auto_drilldown_mode,
        "alternative_sweep": {
            str(alternative): run.audit
            for alternative, run in sorted(sweep_runs.items())
        },
    }
    return LegacyVariableBridgeRun(
        frame=main_run.sequence.frame,
        legacy_frame=main_run.sequence.legacy_frame,
        details_frame=main_run.sequence.details_frame,
        snapshot_frame=main_run.sequence.snapshot_frame,
        candidate_frame=context.candidate_frame,
        candidate_legacy_frame=context.candidate_legacy_frame,
        drilldown_runs=main_run.drilldown_runs,
        moved_run=main_run.moved_run,
        sweep_runs=sweep_runs,
        param=main_run.sequence.param,
        chart=context.chart,
        bridge_dimensions=context.bridge_dimensions,
        audit=audit,
    )


def run_legacy_variable_dimension_component_bridge(
    df: pl.DataFrame,
    recipe: dict[str, Any],
) -> LegacyVariableBridgeRun:
    """Run the legacy component-by-dimension root-cause calculation."""

    report_dimensions = list(recipe["mappings"].get("dimensions") or [])
    requested_calculation_grain = list(
        recipe["mappings"].get("calculation_grain") or []
    )
    bridge_dimensions = _leaf_dimensions(recipe, report_dimensions)
    empty = pl.DataFrame()
    if len(bridge_dimensions) < 2:
        return LegacyVariableBridgeRun(
            frame=empty,
            legacy_frame=empty,
            details_frame=empty,
            snapshot_frame=empty,
            candidate_frame=empty,
            candidate_legacy_frame=empty,
            drilldown_runs={},
            moved_run=None,
            sweep_runs={},
            param={},
            chart={},
            bridge_dimensions=bridge_dimensions,
            audit={
                "enabled": False,
                "reason": "requires at least two dimensions",
                "root_cause_variance_mode": "component_variance",
                "report_dimensions": report_dimensions,
                "calculation_grain": bridge_dimensions,
                **_bridge_dimension_audit(
                    empty,
                    report_dimensions,
                    requested_calculation_grain,
                    bridge_dimensions,
                ),
            },
        )
    if not recipe["mappings"].get("units_column"):
        return LegacyVariableBridgeRun(
            frame=empty,
            legacy_frame=empty,
            details_frame=empty,
            snapshot_frame=empty,
            candidate_frame=empty,
            candidate_legacy_frame=empty,
            drilldown_runs={},
            moved_run=None,
            sweep_runs={},
            param={},
            chart={},
            bridge_dimensions=bridge_dimensions,
            audit={
                "enabled": False,
                "reason": "requires units to calculate price/unit/mix components",
                "root_cause_variance_mode": "component_variance",
                "report_dimensions": report_dimensions,
                "calculation_grain": bridge_dimensions,
                **_bridge_dimension_audit(
                    empty,
                    report_dimensions,
                    requested_calculation_grain,
                    bridge_dimensions,
                ),
            },
        )
    context = _prepare_legacy_variable_bridge_context(
        df,
        recipe,
        variance_mode="component_variance",
    )
    names = context.names
    options = recipe.get("options") or {}
    alternative_result = _bounded_positive_int(
        options.get("root_cause_component_bridge_alternative_result"),
        1,
        maximum=10,
    )
    main_run = _run_prepared_variable_bridge_alternative(
        context,
        options=options,
        alternative_result=alternative_result,
        move_rows={},
        manual_drilldown_rows=[],
        drilldown_all=False,
        auto_drilldown_mode="none",
    )
    dimension_audit = _bridge_dimension_audit(
        context.candidate_frame,
        context.report_dimensions,
        context.requested_calculation_grain,
        context.bridge_dimensions,
    )
    audit = {
        "enabled": True,
        "vendor_root": str(context.imports["vendor_root"]),
        "variable_bridge_source": (
            "modules.variance.index_handling."
            "process_and_prepare_multidimensional_data"
        ),
        "variable_bridge_sequence": (
            "modules.variance.variance_decomposition.process_node_combinations"
        ),
        "legacy_processing_choice": names["runVariableDimensionalAnalysis"],
        "legacy_variance_aggregation": context.chart[names["varianceAggregation"]],
        "root_cause_variance_mode": "component_variance",
        "plugin_variance_aggregation": "component_variance",
        "legacy_sequence_run": names["mainReportRunName"],
        "report_dimensions": report_dimensions,
        "calculation_grain": bridge_dimensions,
        **dimension_audit,
        "legacy_periods": context.config["periodsArray"],
        "alternative_result": alternative_result,
        "candidate_row_count": context.candidate_frame.height,
        "row_count": main_run.sequence.frame.height,
        "sequence_row_count": main_run.sequence.frame.height,
        "selected_sequence_bridge_dimensions": main_run.sequence.audit[
            "selected_sequence_bridge_dimensions"
        ],
        "selected_sequence_unique_bridge_dimensions": main_run.sequence.audit[
            "selected_sequence_unique_bridge_dimensions"
        ],
        "selected_sequence_has_mixed_dimensions": main_run.sequence.audit[
            "selected_sequence_has_mixed_dimensions"
        ],
        "details_row_count": main_run.sequence.details_frame.height,
        "snapshot_row_count": main_run.sequence.snapshot_frame.height,
        "sequence_running_total": main_run.sequence.param.get(
            names["runningTotalName"]
        ),
        "sequence_rows_until_stop": main_run.sequence.param.get(
            names["rowResultsUntilStop"]
        ),
        "drilldown_requested_rows": [],
        "drilldown_invalid_rows": [],
        "drilldown_all": False,
        "drilldown_status": "not_requested",
        "drilldown_row_status": {},
        "drilldown_row_counts": {},
        "moved_rows_requested": {},
        "moved_rows_status": "not_requested",
        "moved_rows_insert_at_row_dict": {},
        "moved_rows_insert_audit": {"inserted": {}, "invalid": {}, "insert_slots": {}},
        "moved_rows_row_count": 0,
        "alternative_sweep_enabled": False,
        "alternative_sweep_values": [],
    }
    return LegacyVariableBridgeRun(
        frame=main_run.sequence.frame,
        legacy_frame=main_run.sequence.legacy_frame,
        details_frame=main_run.sequence.details_frame,
        snapshot_frame=main_run.sequence.snapshot_frame,
        candidate_frame=context.candidate_frame,
        candidate_legacy_frame=context.candidate_legacy_frame,
        drilldown_runs={},
        moved_run=None,
        sweep_runs={},
        param=main_run.sequence.param,
        chart=context.chart,
        bridge_dimensions=context.bridge_dimensions,
        audit=audit,
    )


def run_legacy_variance(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    report_dimensions: list[str],
) -> LegacyVarianceRun:
    """Run legacy period splitting, price-volume-mix calculation, and mix calculation."""

    imports = _legacy_imports()
    names = imports["get_naming_params"]()
    param, chart = _legacy_param_and_chart(recipe, report_dimensions, names)
    leaf_dimensions = _leaf_dimensions(recipe, report_dimensions)
    canonical, value_columns = _canonical_legacy_input(
        df, recipe, names, leaf_dimensions
    )
    period_name = names["periodName"]
    index_columns = [*leaf_dimensions, period_name]
    grouped, param = imports["group_by_df_on_index_cols"](
        canonical.lazy(),
        index_columns.copy(),
        value_columns,
        "sum",
        param,
        False,
    )
    grouped, param = imports["rename_periods"](grouped, param, chart, False)
    grouped = grouped.sort(index_columns)
    grouped, param, _columns = imports["calculate_unit_and_volume_price"](
        grouped, param, []
    )
    grouped, param = imports["calculate_discount_per_units_and_volume"](grouped, param)
    grouped, param = imports["calculate_cogs_per_units_and_volume"](grouped, param)
    pivoted = imports["pivot_lazy_periods"](
        grouped,
        index_cols=index_columns.copy(),
        agg_func="sum",
    ).collect()
    base_legacy_frame, param = imports["calculate_variance"](pivoted, param, chart)
    period_totals, param = _collapse_legacy_rows(
        base_legacy_frame,
        report_dimensions,
        param,
        imports["recalculate_price"],
    )
    legacy_frame = base_legacy_frame
    if recipe["mappings"].get("units_column"):
        legacy_frame = imports["calculate_sales_mix_variance"](
            base_legacy_frame, param, chart, leaf_dimensions
        )
    legacy_frame, param = _collapse_legacy_rows(
        legacy_frame,
        report_dimensions,
        param,
        imports["recalculate_price"],
    )
    legacy_frame = _merge_missing_legacy_columns(
        legacy_frame,
        period_totals,
        report_dimensions,
    )
    normalized = _normalize_legacy_output(legacy_frame, report_dimensions, names)
    audit = {
        "vendor_root": str(imports["vendor_root"]),
        "period_split": "modules.variance.variance_utils.rename_periods",
        "period_pivot": "modules.utilities.helpers.pivot_lazy_periods",
        "variance_formula": "modules.variance.variance_formulas.calculate_variance",
        "mix_formula": (
            "modules.variance.variance_formulas.calculate_sales_mix_variance"
            if recipe["mappings"].get("units_column")
            else None
        ),
        "report_dimensions": report_dimensions or ["segment"],
        "calculation_grain": leaf_dimensions,
        "legacy_periods": imports["get_config_params"]()["periodsArray"],
    }
    return LegacyVarianceRun(frame=normalized, legacy_frame=legacy_frame, audit=audit)
