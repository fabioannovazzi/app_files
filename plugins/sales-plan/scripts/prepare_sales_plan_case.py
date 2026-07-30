#!/usr/bin/env python3
"""Prepare a reviewed Actual-to-Plan sales scenario with exact arithmetic.

The engine is deterministic because exact scenario arithmetic, scope matching,
reconciliation, and replay receipts are mechanically verifiable. Codex and the
commercialista remain responsible for interpreting source columns, choosing
assumptions, resolving currency meaning, and approving professional conclusions.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, Inexact, Rounded, localcontext
from pathlib import Path
from typing import Any

from plan_contract_kernel import (
    ContractValidationError,
    ExactDecimalPolicy,
    canonical_json_sha256,
    decimal_text,
    exact_decimal_context,
    file_sha256,
    file_snapshot_beneath,
    parse_decimal,
    read_exact_csv_snapshot_beneath,
    resolve_local_file,
    strict_json_load,
    write_json,
)

__all__ = [
    "ENGINE_VERSION",
    "RECIPE_ID",
    "main",
    "prepare_sales_plan_case",
    "snapshot_declared_actual_sales",
]

LOGGER = logging.getLogger(__name__)

CASE_SCHEMA = "vera.sales_plan_preparation_case.v2"
RECONCILIATION_SCHEMA = "vera.sales_plan_reconciliation.v2"
MANIFEST_SCHEMA = "vera.sales_plan_evidence_manifest.v2"
RECIPE_ID = "sales_plan_from_reviewed_actuals.v2"
ENGINE_VERSION = "1.1.1"

SOURCE_SCENARIO = "AC"
TARGET_SCENARIO = "PL"
TIME_PROFILE = "base"
FX_RATE_DEFINITION = "reporting_currency_per_transaction_currency"
DRIVER_ORDER = (
    "units_pct",
    "unit_price_pct",
    "gross_sales_pct",
    "discount_pct",
    "cogs_pct",
    "fx_rate_pct",
)
DRIVERS = frozenset(DRIVER_ORDER)
OPTIONAL_METRICS = ("units", "discount_local", "cogs_local")
REQUIRED_METRICS = (
    "source_row_id",
    "period",
    "transaction_currency",
    "gross_sales_local",
    "fx_rate_to_reporting",
)
DEFAULT_BEHAVIORS = frozenset({"proportional_to_sales", "unchanged"})
SAME_DRIVER_OVERLAP_BEHAVIORS = frozenset({"compound", "priority"})
ASSUMPTION_BASES = frozenset({"actual_amount", "sales_adjusted_amount"})
CHECK_IDS = (
    "input_contract",
    "source_row_conservation",
    "period_contract",
    "assumption_scope",
    "assumption_collision",
    "metric_availability",
    "scenario_identity",
    "summary_tie_out",
)
DECIMAL_POLICY = ExactDecimalPolicy(
    max_digits=38,
    max_scale=6,
    calculation_precision=128,
)
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PERIOD_PATTERN = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
UPPER_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

SCENARIO_FIXED_COLUMNS = (
    "row_id",
    "source_row_id",
    "scenario",
    "period",
)
SCENARIO_METRIC_COLUMNS = (
    "transaction_currency",
    "reporting_currency",
    "unit",
    "units",
    "gross_sales_local",
    "discount_local",
    "cogs_local",
    "fx_rate_to_reporting",
    "gross_sales_reporting",
    "discount_reporting",
    "net_sales_reporting",
    "cogs_reporting",
    "gross_margin_reporting",
)
LEDGER_COLUMNS = (
    "ledger_row_id",
    "assumption_id",
    "plan_row_id",
    "source_row_id",
    "target_period",
    "driver",
    "priority",
    "scope_json",
    "change_pct",
    "status",
    "application_mode",
    "overridden_by",
    "driver_value_name",
    "before_value",
    "after_value",
)
SUMMARY_COLUMNS = (
    "summary_level",
    "dimension_name",
    "dimension_value",
    "metric",
    "unit",
    "actual",
    "plan",
    "delta",
    "delta_pct_rounded_4dp",
)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractValidationError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{label} must be text")
    if value != value.strip():
        raise ContractValidationError(f"{label} must not contain edge whitespace")
    if not value and not allow_empty:
        raise ContractValidationError(f"{label} must be non-empty text")
    return value


def _identifier(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if IDENTIFIER_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a canonical identifier")
    return result


def _currency(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if UPPER_CURRENCY_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be an uppercase ISO currency")
    return result


def _period(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if PERIOD_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must use YYYY-MM")
    year, month = result.split("-")
    date(int(year), int(month), 1)
    return result


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    label: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(
            f"{label} contains unexpected fields: {unexpected}"
        )


def _unique_text_list(value: Any, *, label: str) -> list[str]:
    items = [
        _text(item, label=f"{label} item") for item in _sequence(value, label=label)
    ]
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{label} must not contain duplicates")
    return items


def _write_csv(
    path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _artifact_record(artifact_id: str, path: Path, media_type: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path.name,
        "media_type": media_type,
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _add_error(
    errors: list[dict[str, Any]],
    *,
    gate: str,
    code: str,
    message: str,
    identifiers: Sequence[str] = (),
) -> None:
    errors.append(
        {
            "gate": gate,
            "code": code,
            "message": message,
            "identifiers": list(identifiers),
        }
    )


def _checks(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(error["gate"]) for error in errors)
    return [
        {
            "check_id": check_id,
            "status": "failed" if counts[check_id] else "passed",
            "failure_count": counts[check_id],
        }
        for check_id in CHECK_IDS
    ]


def _load_period_mapping(value: Any) -> list[dict[str, str]]:
    raw_items = _sequence(value, label="preparation_recipe.period_mapping")
    if not raw_items or len(raw_items) > 24:
        raise ContractValidationError(
            "preparation_recipe.period_mapping must contain 1 to 24 periods"
        )
    periods: list[dict[str, str]] = []
    for position, raw_item in enumerate(raw_items, start=1):
        item = _mapping(raw_item, label=f"period_mapping[{position}]")
        _exact_fields(
            item,
            required=frozenset({"source_period", "target_period"}),
            label=f"period_mapping[{position}]",
        )
        periods.append(
            {
                "source_period": _period(
                    item["source_period"],
                    label=f"period_mapping[{position}].source_period",
                ),
                "target_period": _period(
                    item["target_period"],
                    label=f"period_mapping[{position}].target_period",
                ),
            }
        )
    source_periods = [item["source_period"] for item in periods]
    target_periods = [item["target_period"] for item in periods]
    if source_periods != sorted(source_periods) or target_periods != sorted(
        target_periods
    ):
        raise ContractValidationError(
            "period_mapping source and target periods must be chronological"
        )
    if len(source_periods) != len(set(source_periods)):
        raise ContractValidationError("period_mapping source periods must be unique")
    if len(target_periods) != len(set(target_periods)):
        raise ContractValidationError("period_mapping target periods must be unique")
    return periods


def _load_metric_columns(value: Any) -> dict[str, str]:
    metrics = _mapping(value, label="preparation_recipe.metric_columns")
    _exact_fields(
        metrics,
        required=frozenset(REQUIRED_METRICS),
        optional=frozenset(OPTIONAL_METRICS),
        label="preparation_recipe.metric_columns",
    )
    result = {
        key: _identifier(column, label=f"metric_columns.{key}")
        for key, column in metrics.items()
    }
    if len(result.values()) != len(set(result.values())):
        raise ContractValidationError("metric column names must be unique")
    return result


def _load_assumptions(
    value: Any,
    *,
    dimensions: Sequence[str],
    target_periods: Sequence[str],
) -> list[dict[str, Any]]:
    review = _mapping(value, label="reviewed_assumptions")
    _exact_fields(
        review,
        required=frozenset(
            {
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_basis",
                "assumptions",
            }
        ),
        label="reviewed_assumptions",
    )
    if review["status"] != "reviewed":
        raise ContractValidationError("reviewed_assumptions.status must be reviewed")
    _text(review["reviewed_by"], label="reviewed_assumptions.reviewed_by")
    reviewed_at = _text(review["reviewed_at"], label="reviewed_assumptions.reviewed_at")
    try:
        date.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ContractValidationError(
            "reviewed_assumptions.reviewed_at must be an ISO date"
        ) from exc
    _text(review["review_basis"], label="reviewed_assumptions.review_basis")

    allowed_scope_fields = {*dimensions, "transaction_currency"}
    assumptions: list[dict[str, Any]] = []
    assumption_ids: set[str] = set()
    for position, raw_assumption in enumerate(
        _sequence(review["assumptions"], label="reviewed_assumptions.assumptions"),
        start=1,
    ):
        assumption = _mapping(raw_assumption, label=f"assumption[{position}]")
        _exact_fields(
            assumption,
            required=frozenset(
                {
                    "assumption_id",
                    "driver",
                    "change_pct",
                    "scope",
                    "effective_periods",
                    "priority",
                    "rationale",
                }
            ),
            label=f"assumption[{position}]",
        )
        assumption_id = _identifier(
            assumption["assumption_id"],
            label=f"assumption[{position}].assumption_id",
        )
        if assumption_id in assumption_ids:
            raise ContractValidationError("assumption_id values must be unique")
        assumption_ids.add(assumption_id)
        driver = _text(assumption["driver"], label=f"{assumption_id}.driver")
        if driver not in DRIVERS:
            raise ContractValidationError(
                f"{assumption_id}.driver must be one of {sorted(DRIVERS)}"
            )
        change_pct = parse_decimal(
            assumption["change_pct"],
            label=f"{assumption_id}.change_pct",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
        if change_pct < Decimal("-100"):
            raise ContractValidationError(
                f"{assumption_id}.change_pct must not be below -100"
            )
        if driver == "fx_rate_pct" and change_pct <= Decimal("-100"):
            raise ContractValidationError(
                f"{assumption_id}.change_pct must keep the FX rate positive"
            )
        scope = _mapping(assumption["scope"], label=f"{assumption_id}.scope")
        unexpected_scope = sorted(set(scope) - allowed_scope_fields)
        if unexpected_scope:
            raise ContractValidationError(
                f"{assumption_id}.scope contains unsupported fields: "
                f"{unexpected_scope}"
            )
        normalized_scope: dict[str, list[str]] = {}
        for field, raw_values in sorted(scope.items()):
            values = _unique_text_list(
                raw_values, label=f"{assumption_id}.scope.{field}"
            )
            if not values:
                raise ContractValidationError(
                    f"{assumption_id}.scope.{field} must not be empty"
                )
            normalized_scope[field] = values
        effective_periods = _unique_text_list(
            assumption["effective_periods"],
            label=f"{assumption_id}.effective_periods",
        )
        if not effective_periods:
            raise ContractValidationError(
                f"{assumption_id}.effective_periods must not be empty"
            )
        unsupported_periods = sorted(set(effective_periods) - set(target_periods))
        if unsupported_periods:
            raise ContractValidationError(
                f"{assumption_id}.effective_periods contains periods outside "
                f"the target horizon: {unsupported_periods}"
            )
        priority = assumption["priority"]
        if type(priority) is not int or not 0 <= priority <= 10000:
            raise ContractValidationError(
                f"{assumption_id}.priority must be an integer from 0 to 10000"
            )
        assumptions.append(
            {
                "assumption_id": assumption_id,
                "driver": driver,
                "change_pct": decimal_text(change_pct),
                "scope": normalized_scope,
                "effective_periods": effective_periods,
                "priority": priority,
                "rationale": _text(
                    assumption["rationale"], label=f"{assumption_id}.rationale"
                ),
            }
        )
    if not assumptions:
        raise ContractValidationError(
            "reviewed_assumptions.assumptions must contain at least one assumption"
        )
    return assumptions


def _load_case(
    case_path: Path,
) -> tuple[
    dict[str, Any],
    Path,
    str,
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, str]],
    list[str],
    dict[str, str],
]:
    case_path = Path(case_path).resolve()
    case = strict_json_load(case_path)
    _exact_fields(
        case,
        required=frozenset(
            {
                "schema_version",
                "case_id",
                "purpose",
                "preparation_recipe",
                "reviewed_assumptions",
                "files",
                "professional_boundary",
            }
        ),
        label="sales plan case",
    )
    if case["schema_version"] != CASE_SCHEMA:
        raise ContractValidationError(f"schema_version must be {CASE_SCHEMA}")
    _identifier(case["case_id"], label="case_id")
    _text(case["purpose"], label="purpose")

    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    _exact_fields(
        recipe,
        required=frozenset(
            {
                "recipe_id",
                "engine_version",
                "arithmetic",
                "source_scenario",
                "target_scenario",
                "reporting_currency",
                "unit",
                "time_profile",
                "period_mapping",
                "dimension_columns",
                "metric_columns",
                "default_discount_behavior",
                "default_cogs_behavior",
                "same_driver_overlap_behavior",
                "discount_assumption_basis",
                "cogs_assumption_basis",
                "fx_rate_definition",
            }
        ),
        label="preparation_recipe",
    )
    if recipe["recipe_id"] != RECIPE_ID:
        raise ContractValidationError(
            f"preparation_recipe.recipe_id must be {RECIPE_ID}"
        )
    if recipe["engine_version"] != ENGINE_VERSION:
        raise ContractValidationError(
            f"preparation_recipe.engine_version must be {ENGINE_VERSION}"
        )
    if recipe["arithmetic"] != "decimal_exact":
        raise ContractValidationError(
            "preparation_recipe.arithmetic must be decimal_exact"
        )
    if recipe["source_scenario"] != SOURCE_SCENARIO:
        raise ContractValidationError(
            f"preparation_recipe.source_scenario must be {SOURCE_SCENARIO}"
        )
    if recipe["target_scenario"] != TARGET_SCENARIO:
        raise ContractValidationError(
            f"preparation_recipe.target_scenario must be {TARGET_SCENARIO}"
        )
    _currency(
        recipe["reporting_currency"],
        label="preparation_recipe.reporting_currency",
    )
    _text(recipe["unit"], label="preparation_recipe.unit")
    if recipe["time_profile"] != TIME_PROFILE:
        raise ContractValidationError(
            "sales_plan_from_reviewed_actuals.v2 supports only base time profile"
        )
    if recipe["fx_rate_definition"] != FX_RATE_DEFINITION:
        raise ContractValidationError(
            f"preparation_recipe.fx_rate_definition must be {FX_RATE_DEFINITION}"
        )
    for field in ("default_discount_behavior", "default_cogs_behavior"):
        if recipe[field] not in DEFAULT_BEHAVIORS:
            raise ContractValidationError(
                f"preparation_recipe.{field} must be one of "
                f"{sorted(DEFAULT_BEHAVIORS)}"
            )
    if recipe["same_driver_overlap_behavior"] not in SAME_DRIVER_OVERLAP_BEHAVIORS:
        raise ContractValidationError(
            "preparation_recipe.same_driver_overlap_behavior must be one of "
            f"{sorted(SAME_DRIVER_OVERLAP_BEHAVIORS)}"
        )
    for field in ("discount_assumption_basis", "cogs_assumption_basis"):
        if recipe[field] not in ASSUMPTION_BASES:
            raise ContractValidationError(
                f"preparation_recipe.{field} must be one of "
                f"{sorted(ASSUMPTION_BASES)}"
            )
    period_mapping = _load_period_mapping(recipe["period_mapping"])
    dimensions = _unique_text_list(
        recipe["dimension_columns"],
        label="preparation_recipe.dimension_columns",
    )
    dimensions = [_identifier(item, label="dimension column") for item in dimensions]
    if len(dimensions) > 8:
        raise ContractValidationError("at most eight dimension columns are supported")
    metrics = _load_metric_columns(recipe["metric_columns"])
    reserved_columns = set(metrics.values())
    collisions = sorted(set(dimensions) & reserved_columns)
    if collisions:
        raise ContractValidationError(
            f"dimension columns collide with metric columns: {collisions}"
        )
    assumptions = _load_assumptions(
        case["reviewed_assumptions"],
        dimensions=dimensions,
        target_periods=[item["target_period"] for item in period_mapping],
    )

    files = _mapping(case["files"], label="files")
    _exact_fields(
        files,
        required=frozenset({"actual_sales"}),
        label="files",
    )
    actual_receipt = _mapping(files["actual_sales"], label="files.actual_sales")
    _exact_fields(
        actual_receipt,
        required=frozenset({"path", "sha256"}),
        label="files.actual_sales",
    )
    actual_path = resolve_local_file(
        case_path.parent,
        actual_receipt["path"],
        label="files.actual_sales.path",
    )
    expected_sha256 = _text(actual_receipt["sha256"], label="files.actual_sales.sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ContractValidationError(
            "files.actual_sales.sha256 must be a lowercase SHA-256 digest"
        )

    boundary = _mapping(case["professional_boundary"], label="professional_boundary")
    _exact_fields(
        boundary,
        required=frozenset(
            {
                "prospective_assumptions_are_not_source_facts",
                "professional_approval_required",
                "report_ready",
            }
        ),
        label="professional_boundary",
    )
    if boundary != {
        "prospective_assumptions_are_not_source_facts": True,
        "professional_approval_required": True,
        "report_ready": False,
    }:
        raise ContractValidationError(
            "professional_boundary must keep assumptions prospective, require "
            "professional approval, and set report_ready=false"
        )
    return (
        case,
        actual_path,
        expected_sha256,
        dict(recipe),
        assumptions,
        period_mapping,
        dimensions,
        metrics,
    )


def _source_columns(
    dimensions: Sequence[str], metrics: Mapping[str, str]
) -> tuple[str, ...]:
    columns = [
        metrics["source_row_id"],
        metrics["period"],
        *dimensions,
        metrics["transaction_currency"],
    ]
    if "units" in metrics:
        columns.append(metrics["units"])
    columns.append(metrics["gross_sales_local"])
    if "discount_local" in metrics:
        columns.append(metrics["discount_local"])
    if "cogs_local" in metrics:
        columns.append(metrics["cogs_local"])
    columns.append(metrics["fx_rate_to_reporting"])
    return tuple(columns)


def _read_source_rows(
    path: Path,
    *,
    source_root: Path,
    expected_sha256: str,
    reporting_currency: str,
    dimensions: Sequence[str],
    metrics: Mapping[str, str],
    period_mapping: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, Any]]:
    raw_rows, source_byte_count, source_sha256 = read_exact_csv_snapshot_beneath(
        path,
        root=source_root,
        columns=_source_columns(dimensions, metrics),
        label="actual sales",
    )
    if source_sha256 != expected_sha256:
        raise ContractValidationError("files.actual_sales.sha256 is stale")
    source_periods = {item["source_period"] for item in period_mapping}
    source_row_ids: set[str] = set()
    group_periods: dict[tuple[str, ...], set[str]] = defaultdict(set)
    rows: list[dict[str, Any]] = []
    for position, raw_row in enumerate(raw_rows, start=2):
        source_row_id = _identifier(
            raw_row[metrics["source_row_id"]],
            label=f"actual sales row {position} source_row_id",
        )
        if source_row_id in source_row_ids:
            raise ContractValidationError(
                "actual sales source_row_id values must be unique"
            )
        source_row_ids.add(source_row_id)
        period = _period(
            raw_row[metrics["period"]],
            label=f"actual sales row {position} period",
        )
        if period not in source_periods:
            raise ContractValidationError(
                f"actual sales row {position} period is outside period_mapping"
            )
        dimension_values = {
            dimension: _text(
                raw_row[dimension],
                label=f"actual sales row {position} {dimension}",
            )
            for dimension in dimensions
        }
        transaction_currency = _currency(
            raw_row[metrics["transaction_currency"]],
            label=f"actual sales row {position} transaction_currency",
        )
        units: Decimal | None = None
        if "units" in metrics:
            units_text = raw_row[metrics["units"]]
            if units_text:
                units = parse_decimal(
                    units_text,
                    label=f"actual sales row {position} units",
                    policy=DECIMAL_POLICY,
                    non_negative=True,
                    canonical=True,
                )
        gross_sales_local = parse_decimal(
            raw_row[metrics["gross_sales_local"]],
            label=f"actual sales row {position} gross_sales_local",
            policy=DECIMAL_POLICY,
            non_negative=True,
            canonical=True,
        )
        discount_local: Decimal | None = None
        if "discount_local" in metrics:
            discount_text = raw_row[metrics["discount_local"]]
            if discount_text:
                discount_local = parse_decimal(
                    discount_text,
                    label=f"actual sales row {position} discount_local",
                    policy=DECIMAL_POLICY,
                    non_negative=True,
                    canonical=True,
                )
        cogs_local: Decimal | None = None
        if "cogs_local" in metrics:
            cogs_text = raw_row[metrics["cogs_local"]]
            if cogs_text:
                cogs_local = parse_decimal(
                    cogs_text,
                    label=f"actual sales row {position} cogs_local",
                    policy=DECIMAL_POLICY,
                    non_negative=True,
                    canonical=True,
                )
        fx_rate = parse_decimal(
            raw_row[metrics["fx_rate_to_reporting"]],
            label=f"actual sales row {position} fx_rate_to_reporting",
            policy=DECIMAL_POLICY,
            positive=True,
            canonical=True,
        )
        if transaction_currency == reporting_currency and fx_rate != Decimal(1):
            raise ContractValidationError(
                f"actual sales row {position} fx_rate_to_reporting must equal 1 "
                "when transaction currency equals reporting currency"
            )
        group_key = tuple(
            [
                *(dimension_values[dimension] for dimension in dimensions),
                transaction_currency,
            ]
        )
        if period in group_periods[group_key]:
            raise ContractValidationError(
                "actual sales must contain at most one row per period and declared "
                f"dimension grain; duplicate group at row {position}"
            )
        group_periods[group_key].add(period)
        rows.append(
            {
                "source_row_id": source_row_id,
                "period": period,
                **dimension_values,
                "transaction_currency": transaction_currency,
                "units": units,
                "gross_sales_local": gross_sales_local,
                "discount_local": discount_local,
                "cogs_local": cogs_local,
                "fx_rate_to_reporting": fx_rate,
            }
        )
    expected_periods = set(source_periods)
    missing_period_count = sum(
        len(expected_periods - observed_periods)
        for observed_periods in group_periods.values()
    )
    source_profile = {
        "declared_grains": len(group_periods),
        "sparse_grains": sum(
            observed_periods != expected_periods
            for observed_periods in group_periods.values()
        ),
        "missing_grain_periods": missing_period_count,
    }
    source_snapshot = {
        "byte_count": source_byte_count,
        "sha256": source_sha256,
    }
    return rows, source_profile, source_snapshot


def _require_unchanged_source(
    path: Path,
    *,
    source_root: Path,
    byte_count: int,
    sha256: str,
) -> None:
    current_byte_count, current_sha256 = file_snapshot_beneath(
        path,
        root=source_root,
    )
    if current_byte_count != byte_count or current_sha256 != sha256:
        raise ContractValidationError(
            "actual sales source changed during Plan execution"
        )


def snapshot_declared_actual_sales(case_path: Path) -> tuple[Path, int, str]:
    """Resolve and snapshot the case-bound Actual sales source."""

    resolved_case_path = Path(case_path).resolve()
    (
        _case,
        source_path,
        expected_sha256,
        _recipe,
        _assumptions,
        _period_mapping,
        _dimensions,
        _metrics,
    ) = _load_case(resolved_case_path)
    byte_count, sha256 = file_snapshot_beneath(
        source_path,
        root=resolved_case_path.parent,
    )
    if sha256 != expected_sha256:
        raise ContractValidationError("files.actual_sales.sha256 is stale")
    return source_path, byte_count, sha256


def _matches(
    assumption: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    target_period: str,
) -> bool:
    if target_period not in assumption["effective_periods"]:
        return False
    scope = _mapping(assumption["scope"], label="assumption scope")
    return all(str(row[field]) in values for field, values in scope.items())


def _select_assumptions(
    assumptions: Sequence[Mapping[str, Any]],
    row: Mapping[str, Any],
    *,
    target_period: str,
    same_driver_overlap_behavior: str,
    errors: list[dict[str, Any]],
) -> tuple[
    dict[str, list[Mapping[str, Any]]],
    dict[str, list[Mapping[str, Any]]],
]:
    selected: dict[str, list[Mapping[str, Any]]] = {}
    candidates_by_driver: dict[str, list[Mapping[str, Any]]] = {}
    for driver in DRIVER_ORDER:
        candidates = [
            assumption
            for assumption in assumptions
            if assumption["driver"] == driver
            and _matches(assumption, row, target_period=target_period)
        ]
        candidates_by_driver[driver] = candidates
        if not candidates:
            continue
        ordered_candidates = sorted(
            candidates,
            key=lambda item: (
                -int(item["priority"]),
                str(item["assumption_id"]),
            ),
        )
        if same_driver_overlap_behavior == "compound":
            selected[driver] = ordered_candidates
            continue
        highest_priority = max(int(item["priority"]) for item in candidates)
        winners = [
            item for item in candidates if int(item["priority"]) == highest_priority
        ]
        if len(winners) > 1:
            _add_error(
                errors,
                gate="assumption_collision",
                code="ambiguous_same_priority_assumptions",
                message=(
                    f"{row['source_row_id']} {target_period} has multiple "
                    f"{driver} assumptions at priority {highest_priority}"
                ),
                identifiers=[
                    str(row["source_row_id"]),
                    target_period,
                    driver,
                    *(str(item["assumption_id"]) for item in winners),
                ],
            )
            continue
        selected[driver] = winners
    if "gross_sales_pct" in selected and (
        "units_pct" in selected or "unit_price_pct" in selected
    ):
        _add_error(
            errors,
            gate="assumption_collision",
            code="direct_sales_and_driver_overlap",
            message=(
                f"{row['source_row_id']} {target_period} combines direct sales "
                "with units or price assumptions"
            ),
            identifiers=[
                str(row["source_row_id"]),
                target_period,
                "gross_sales_pct",
            ],
        )
    return selected, candidates_by_driver


def _multiplier(assumption: Mapping[str, Any] | None) -> Decimal:
    if assumption is None:
        return Decimal(1)
    return Decimal(1) + (
        parse_decimal(
            assumption["change_pct"],
            label=f"{assumption['assumption_id']}.change_pct",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
        / Decimal(100)
    )


def _combined_multiplier(
    assumptions: Sequence[Mapping[str, Any]],
) -> Decimal:
    """Multiply reviewed percentage effects with exact arithmetic."""

    result = Decimal(1)
    for assumption in assumptions:
        result *= _multiplier(assumption)
    return result


def _application_stages(
    base_value: Decimal | None,
    assumptions: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Decimal | None, Decimal | None]]:
    """Record deterministic priority-and-ID ledger stages for compounded effects."""

    stages: dict[str, tuple[Decimal | None, Decimal | None]] = {}
    current = base_value
    for assumption in assumptions:
        after = None if current is None else current * _multiplier(assumption)
        stages[str(assumption["assumption_id"])] = (current, after)
        current = after
    return stages


def _derived_reporting_metrics(
    *,
    gross_sales_local: Decimal,
    discount_local: Decimal | None,
    cogs_local: Decimal | None,
    fx_rate: Decimal,
) -> dict[str, Decimal | None]:
    gross_sales_reporting = gross_sales_local * fx_rate
    discount_reporting = (
        discount_local * fx_rate if discount_local is not None else None
    )
    net_sales_reporting = gross_sales_reporting - (discount_reporting or Decimal(0))
    cogs_reporting = cogs_local * fx_rate if cogs_local is not None else None
    gross_margin_reporting = (
        net_sales_reporting - cogs_reporting if cogs_reporting is not None else None
    )
    return {
        "gross_sales_reporting": gross_sales_reporting,
        "discount_reporting": discount_reporting,
        "net_sales_reporting": net_sales_reporting,
        "cogs_reporting": cogs_reporting,
        "gross_margin_reporting": gross_margin_reporting,
    }


def _scenario_row(
    *,
    row_id: str,
    source_row_id: str,
    scenario: str,
    period: str,
    dimensions: Sequence[str],
    source_row: Mapping[str, Any],
    reporting_currency: str,
    unit: str,
    units: Decimal | None,
    gross_sales_local: Decimal,
    discount_local: Decimal | None,
    cogs_local: Decimal | None,
    fx_rate: Decimal,
) -> dict[str, str]:
    derived = _derived_reporting_metrics(
        gross_sales_local=gross_sales_local,
        discount_local=discount_local,
        cogs_local=cogs_local,
        fx_rate=fx_rate,
    )

    def optional_decimal(value: Decimal | None) -> str:
        return "" if value is None else decimal_text(value)

    return {
        "row_id": row_id,
        "source_row_id": source_row_id,
        "scenario": scenario,
        "period": period,
        **{dimension: str(source_row[dimension]) for dimension in dimensions},
        "transaction_currency": str(source_row["transaction_currency"]),
        "reporting_currency": reporting_currency,
        "unit": unit,
        "units": optional_decimal(units),
        "gross_sales_local": decimal_text(gross_sales_local),
        "discount_local": optional_decimal(discount_local),
        "cogs_local": optional_decimal(cogs_local),
        "fx_rate_to_reporting": decimal_text(fx_rate),
        **{key: optional_decimal(value) for key, value in derived.items()},
    }


def _ledger_row(
    *,
    assumption: Mapping[str, Any],
    plan_row_id: str,
    source_row_id: str,
    target_period: str,
    status: str,
    application_mode: str,
    overridden_by: str,
    driver_value_name: str,
    before_value: Decimal | None,
    after_value: Decimal | None,
) -> dict[str, str]:
    assumption_id = str(assumption["assumption_id"])
    return {
        "ledger_row_id": (f"{plan_row_id}-{assumption_id}-{status}".replace("_", "-")),
        "assumption_id": assumption_id,
        "plan_row_id": plan_row_id,
        "source_row_id": source_row_id,
        "target_period": target_period,
        "driver": str(assumption["driver"]),
        "priority": str(assumption["priority"]),
        "scope_json": json.dumps(
            assumption["scope"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "change_pct": str(assumption["change_pct"]),
        "status": status,
        "application_mode": application_mode,
        "overridden_by": overridden_by,
        "driver_value_name": driver_value_name,
        "before_value": "" if before_value is None else decimal_text(before_value),
        "after_value": "" if after_value is None else decimal_text(after_value),
    }


def _build_scenarios(
    source_rows: Sequence[Mapping[str, Any]],
    *,
    dimensions: Sequence[str],
    period_mapping: Sequence[Mapping[str, str]],
    assumptions: Sequence[Mapping[str, Any]],
    recipe: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, dict[str, int]],
]:
    target_by_source = {
        str(item["source_period"]): str(item["target_period"])
        for item in period_mapping
    }
    reporting_currency = str(recipe["reporting_currency"])
    unit = str(recipe["unit"])
    scenario_rows: list[dict[str, str]] = []
    ledger_rows: list[dict[str, str]] = []
    assumption_counts = {
        str(assumption["assumption_id"]): {
            "exact_match_count": 0,
            "applied_count": 0,
            "overridden_count": 0,
        }
        for assumption in assumptions
    }

    for source_row in source_rows:
        source_row_id = str(source_row["source_row_id"])
        target_period = target_by_source[str(source_row["period"])]
        actual_row_id = f"AC-{source_row_id}"
        plan_row_id = f"PL-{source_row_id}-{target_period}"
        scenario_rows.append(
            _scenario_row(
                row_id=actual_row_id,
                source_row_id=source_row_id,
                scenario=SOURCE_SCENARIO,
                period=str(source_row["period"]),
                dimensions=dimensions,
                source_row=source_row,
                reporting_currency=reporting_currency,
                unit=unit,
                units=source_row["units"],
                gross_sales_local=source_row["gross_sales_local"],
                discount_local=source_row["discount_local"],
                cogs_local=source_row["cogs_local"],
                fx_rate=source_row["fx_rate_to_reporting"],
            )
        )
        selected, candidates_by_driver = _select_assumptions(
            assumptions,
            source_row,
            target_period=target_period,
            same_driver_overlap_behavior=str(recipe["same_driver_overlap_behavior"]),
            errors=errors,
        )
        for candidates in candidates_by_driver.values():
            for candidate in candidates:
                assumption_counts[str(candidate["assumption_id"])][
                    "exact_match_count"
                ] += 1

        units = source_row["units"]
        gross_sales_local = source_row["gross_sales_local"]
        discount_local = source_row["discount_local"]
        cogs_local = source_row["cogs_local"]
        fx_rate = source_row["fx_rate_to_reporting"]
        transaction_currency = str(source_row["transaction_currency"])

        units_assumptions = selected.get("units_pct", [])
        price_assumptions = selected.get("unit_price_pct", [])
        direct_sales_assumptions = selected.get("gross_sales_pct", [])
        discount_assumptions = selected.get("discount_pct", [])
        cogs_assumptions = selected.get("cogs_pct", [])
        fx_assumptions = selected.get("fx_rate_pct", [])

        if (units_assumptions or price_assumptions) and (units is None or units == 0):
            _add_error(
                errors,
                gate="metric_availability",
                code="units_required_for_volume_or_price_driver",
                message=(
                    f"{source_row_id} requires a positive Units value for the "
                    "selected units or unit-price assumption"
                ),
                identifiers=[source_row_id, target_period],
            )
        if discount_assumptions and discount_local is None:
            _add_error(
                errors,
                gate="metric_availability",
                code="discount_metric_missing",
                message=f"{source_row_id} has a discount assumption but no discount value",
                identifiers=[source_row_id, target_period],
            )
        if cogs_assumptions and cogs_local is None:
            _add_error(
                errors,
                gate="metric_availability",
                code="cogs_metric_missing",
                message=f"{source_row_id} has a COGS assumption but no COGS value",
                identifiers=[source_row_id, target_period],
            )

        units_multiplier = _combined_multiplier(units_assumptions)
        price_multiplier = _combined_multiplier(price_assumptions)
        direct_sales_multiplier = _combined_multiplier(direct_sales_assumptions)
        discount_multiplier = _combined_multiplier(discount_assumptions)
        cogs_multiplier = _combined_multiplier(cogs_assumptions)
        fx_multiplier = _combined_multiplier(fx_assumptions)

        plan_units = units * units_multiplier if units is not None else None
        if direct_sales_assumptions:
            sales_multiplier = direct_sales_multiplier
        else:
            sales_multiplier = units_multiplier * price_multiplier
        plan_gross_sales_local = gross_sales_local * sales_multiplier
        if discount_local is not None:
            discount_assumption_base = discount_local * (
                sales_multiplier
                if recipe["discount_assumption_basis"] == "sales_adjusted_amount"
                else Decimal(1)
            )
            plan_discount_local = (
                discount_assumption_base * discount_multiplier
                if discount_assumptions
                else discount_local
                * (
                    sales_multiplier
                    if recipe["default_discount_behavior"] == "proportional_to_sales"
                    else Decimal(1)
                )
            )
        else:
            discount_assumption_base = None
            plan_discount_local = None
        if cogs_local is not None:
            cogs_assumption_base = cogs_local * (
                sales_multiplier
                if recipe["cogs_assumption_basis"] == "sales_adjusted_amount"
                else Decimal(1)
            )
            plan_cogs_local = (
                cogs_assumption_base * cogs_multiplier
                if cogs_assumptions
                else cogs_local
                * (
                    sales_multiplier
                    if recipe["default_cogs_behavior"] == "proportional_to_sales"
                    else Decimal(1)
                )
            )
        else:
            cogs_assumption_base = None
            plan_cogs_local = None
        plan_fx_rate = fx_rate * fx_multiplier
        if transaction_currency == reporting_currency and plan_fx_rate != Decimal(1):
            _add_error(
                errors,
                gate="assumption_scope",
                code="same_currency_fx_changed",
                message=(
                    f"{source_row_id} {target_period} changes the "
                    f"{reporting_currency}-to-{reporting_currency} FX rate"
                ),
                identifiers=[
                    source_row_id,
                    target_period,
                    *(str(item["assumption_id"]) for item in fx_assumptions),
                ],
            )

        driver_value_names = {
            "units_pct": "units",
            "unit_price_pct": "gross_sales_local_after_units_before_price",
            "gross_sales_pct": "gross_sales_local",
            "discount_pct": (
                "discount_local_after_sales"
                if recipe["discount_assumption_basis"] == "sales_adjusted_amount"
                else "discount_local"
            ),
            "cogs_pct": (
                "cogs_local_after_sales"
                if recipe["cogs_assumption_basis"] == "sales_adjusted_amount"
                else "cogs_local"
            ),
            "fx_rate_pct": "fx_rate_to_reporting",
        }
        application_stages = {
            "units_pct": _application_stages(units, units_assumptions),
            "unit_price_pct": _application_stages(
                gross_sales_local * units_multiplier,
                price_assumptions,
            ),
            "gross_sales_pct": _application_stages(
                gross_sales_local,
                direct_sales_assumptions,
            ),
            "discount_pct": _application_stages(
                discount_assumption_base,
                discount_assumptions,
            ),
            "cogs_pct": _application_stages(
                cogs_assumption_base,
                cogs_assumptions,
            ),
            "fx_rate_pct": _application_stages(fx_rate, fx_assumptions),
        }
        for driver in DRIVER_ORDER:
            applied = selected.get(driver, [])
            applied_ids = {str(assumption["assumption_id"]) for assumption in applied}
            candidates = candidates_by_driver[driver]
            for candidate in sorted(
                candidates,
                key=lambda item: (
                    -int(item["priority"]),
                    str(item["assumption_id"]),
                ),
            ):
                candidate_id = str(candidate["assumption_id"])
                if candidate_id in applied_ids:
                    before_value, after_value = application_stages[driver][candidate_id]
                    value_name = driver_value_names[driver]
                    status = "applied"
                    application_mode = "compound" if len(applied) > 1 else "single"
                    overridden_by = ""
                    assumption_counts[candidate_id]["applied_count"] += 1
                else:
                    value_name, before_value, after_value = ("", None, None)
                    status = "overridden"
                    application_mode = "overridden"
                    overridden_by = (
                        "" if not applied else str(applied[0]["assumption_id"])
                    )
                    assumption_counts[candidate_id]["overridden_count"] += 1
                ledger_rows.append(
                    _ledger_row(
                        assumption=candidate,
                        plan_row_id=plan_row_id,
                        source_row_id=source_row_id,
                        target_period=target_period,
                        status=status,
                        application_mode=application_mode,
                        overridden_by=overridden_by,
                        driver_value_name=value_name,
                        before_value=before_value,
                        after_value=after_value,
                    )
                )

        scenario_rows.append(
            _scenario_row(
                row_id=plan_row_id,
                source_row_id=source_row_id,
                scenario=TARGET_SCENARIO,
                period=target_period,
                dimensions=dimensions,
                source_row=source_row,
                reporting_currency=reporting_currency,
                unit=unit,
                units=plan_units,
                gross_sales_local=plan_gross_sales_local,
                discount_local=plan_discount_local,
                cogs_local=plan_cogs_local,
                fx_rate=plan_fx_rate,
            )
        )

    scenario_rows.sort(
        key=lambda row: (
            row["scenario"],
            row["period"],
            *(row[dimension] for dimension in dimensions),
            row["source_row_id"],
        )
    )
    ledger_rows.sort(
        key=lambda row: (
            row["target_period"],
            row["plan_row_id"],
            DRIVER_ORDER.index(row["driver"]),
            -int(row["priority"]),
            row["assumption_id"],
        )
    )
    return scenario_rows, ledger_rows, assumption_counts


def _rounded_pct(delta: Decimal, actual: Decimal) -> str:
    if actual == 0:
        return ""
    with localcontext() as context:
        context.prec = 64
        context.rounding = ROUND_HALF_UP
        context.traps[Inexact] = False
        context.traps[Rounded] = False
        result = ((delta / actual) * Decimal(100)).quantize(Decimal("0.0001"))
    return decimal_text(result)


def _build_summary(
    scenario_rows: Sequence[Mapping[str, str]],
    *,
    dimensions: Sequence[str],
    unit: str,
) -> list[dict[str, str]]:
    metrics = [
        "units",
        "gross_sales_reporting",
        "discount_reporting",
        "net_sales_reporting",
        "cogs_reporting",
        "gross_margin_reporting",
    ]
    levels: list[tuple[str, str]] = [("total", "")]
    levels.extend(("dimension", dimension) for dimension in dimensions)
    levels.append(("dimension", "transaction_currency"))
    totals: dict[tuple[str, str, str, str, str], Decimal] = defaultdict(Decimal)
    observed: set[tuple[str, str, str, str, str]] = set()
    for row in scenario_rows:
        scenario = row["scenario"]
        for summary_level, dimension_name in levels:
            dimension_value = "" if summary_level == "total" else row[dimension_name]
            for metric in metrics:
                value = row[metric]
                if value == "":
                    continue
                key = (
                    summary_level,
                    dimension_name,
                    dimension_value,
                    metric,
                    scenario,
                )
                totals[key] += Decimal(value)
                observed.add(key)

    base_keys = sorted(
        {
            (level, name, value, metric)
            for level, name, value, metric, _scenario in observed
        }
    )
    rows: list[dict[str, str]] = []
    for level, name, value, metric in base_keys:
        actual = totals.get((level, name, value, metric, SOURCE_SCENARIO))
        plan = totals.get((level, name, value, metric, TARGET_SCENARIO))
        if actual is None and plan is None:
            continue
        actual_value = actual or Decimal(0)
        plan_value = plan or Decimal(0)
        delta = plan_value - actual_value
        rows.append(
            {
                "summary_level": level,
                "dimension_name": name,
                "dimension_value": value,
                "metric": metric,
                "unit": "count" if metric == "units" else unit,
                "actual": decimal_text(actual_value),
                "plan": decimal_text(plan_value),
                "delta": decimal_text(delta),
                "delta_pct_rounded_4dp": _rounded_pct(delta, actual_value),
            }
        )
    return rows


def _summary_totals(
    summary_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "metric": row["metric"],
            "unit": row["unit"],
            "actual": row["actual"],
            "plan": row["plan"],
            "delta": row["delta"],
        }
        for row in summary_rows
        if row["summary_level"] == "total"
    ]


def _prepare_sales_plan_case_exact(case_path: Path, output_dir: Path) -> dict[str, Any]:
    case_path = Path(case_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "sales_plan_scenario": output_dir / "sales_plan_scenario.csv",
        "assumption_application_ledger": (
            output_dir / "assumption_application_ledger.csv"
        ),
        "scenario_summary": output_dir / "scenario_summary.csv",
        "reconciliation": output_dir / "reconciliation.json",
        "prepared_evidence_manifest": output_dir / "prepared_evidence_manifest.json",
    }
    for path in output_paths.values():
        path.unlink(missing_ok=True)

    (
        case,
        source_path,
        expected_source_sha256,
        recipe,
        assumptions,
        period_mapping,
        dimensions,
        metrics,
    ) = _load_case(case_path)
    source_rows, source_profile, source_snapshot = _read_source_rows(
        source_path,
        source_root=case_path.parent,
        expected_sha256=expected_source_sha256,
        reporting_currency=str(recipe["reporting_currency"]),
        dimensions=dimensions,
        metrics=metrics,
        period_mapping=period_mapping,
    )
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if source_profile["sparse_grains"]:
        warnings.append(
            {
                "code": "sparse_source_time_profile",
                "message": (
                    f"{source_profile['sparse_grains']} source grain(s) omit "
                    f"{source_profile['missing_grain_periods']} mapped period(s); "
                    "the Plan preserves observed rows without imputing zero sales"
                ),
                "identifiers": [],
            }
        )
    scenario_rows, ledger_rows, assumption_counts = _build_scenarios(
        source_rows,
        dimensions=dimensions,
        period_mapping=period_mapping,
        assumptions=assumptions,
        recipe=recipe,
        errors=errors,
    )
    for assumption in assumptions:
        assumption_id = str(assumption["assumption_id"])
        counts = assumption_counts[assumption_id]
        if counts["exact_match_count"] == 0:
            _add_error(
                errors,
                gate="assumption_scope",
                code="unmatched_assumption",
                message=f"{assumption_id} did not match any target row",
                identifiers=[assumption_id],
            )
        elif counts["applied_count"] == 0:
            warnings.append(
                {
                    "code": "fully_overridden_assumption",
                    "message": (
                        f"{assumption_id} matched rows but was always overridden "
                        "by a higher-priority assumption"
                    ),
                    "identifiers": [assumption_id],
                }
            )

    summary_rows = _build_summary(
        scenario_rows,
        dimensions=dimensions,
        unit=str(recipe["unit"]),
    )
    if len(scenario_rows) != len(source_rows) * 2:
        _add_error(
            errors,
            gate="source_row_conservation",
            code="scenario_row_count_mismatch",
            message="Actual and Plan output rows do not conserve source rows",
        )
    total_summary_metrics = {
        row["metric"] for row in summary_rows if row["summary_level"] == "total"
    }
    if "gross_sales_reporting" not in total_summary_metrics:
        _add_error(
            errors,
            gate="summary_tie_out",
            code="missing_total_sales_summary",
            message="scenario summary is missing total gross sales",
        )
    _require_unchanged_source(
        source_path,
        source_root=case_path.parent,
        byte_count=int(source_snapshot["byte_count"]),
        sha256=str(source_snapshot["sha256"]),
    )

    errors.sort(
        key=lambda item: (
            str(item["gate"]),
            str(item["code"]),
            str(item["message"]),
            json.dumps(item["identifiers"], sort_keys=True),
        )
    )
    warnings.sort(
        key=lambda item: (
            str(item["code"]),
            str(item["message"]),
            json.dumps(item["identifiers"], sort_keys=True),
        )
    )
    status = "passed" if not errors else "failed"
    assumption_results = [
        {
            "assumption_id": str(assumption["assumption_id"]),
            "driver": str(assumption["driver"]),
            **assumption_counts[str(assumption["assumption_id"])],
            "status": (
                "failed"
                if assumption_counts[str(assumption["assumption_id"])][
                    "exact_match_count"
                ]
                == 0
                else (
                    "qualified"
                    if assumption_counts[str(assumption["assumption_id"])][
                        "applied_count"
                    ]
                    == 0
                    else "passed"
                )
            ),
        }
        for assumption in assumptions
    ]
    reconciliation: dict[str, Any] = {
        "schema_version": RECONCILIATION_SCHEMA,
        "case_id": str(case["case_id"]),
        "recipe": {
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "arithmetic": "decimal_exact",
        },
        "scope": {
            "source_scenario": SOURCE_SCENARIO,
            "target_scenario": TARGET_SCENARIO,
            "reporting_currency": str(recipe["reporting_currency"]),
            "unit": str(recipe["unit"]),
            "time_profile": TIME_PROFILE,
            "same_driver_overlap_behavior": str(recipe["same_driver_overlap_behavior"]),
            "discount_assumption_basis": str(recipe["discount_assumption_basis"]),
            "cogs_assumption_basis": str(recipe["cogs_assumption_basis"]),
            "source_periods": [str(item["source_period"]) for item in period_mapping],
            "target_periods": [str(item["target_period"]) for item in period_mapping],
        },
        "source_profile": source_profile,
        "status": status,
        "report_ready": False,
        "counts": {
            "source_rows": len(source_rows),
            "actual_rows": sum(
                row["scenario"] == SOURCE_SCENARIO for row in scenario_rows
            ),
            "plan_rows": sum(
                row["scenario"] == TARGET_SCENARIO for row in scenario_rows
            ),
            "scenario_rows": len(scenario_rows),
            "ledger_rows": len(ledger_rows),
            "summary_rows": len(summary_rows),
            "assumptions": len(assumptions),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "checks": _checks(errors),
        "assumption_results": assumption_results,
        "scenario_totals": _summary_totals(summary_rows),
        "errors": errors,
        "warnings": warnings,
        "professional_boundary": {
            "prospective_assumptions_are_not_source_facts": True,
            "professional_approval_required": True,
            "report_ready": False,
        },
    }

    if errors:
        write_json(output_paths["reconciliation"], reconciliation)
        _require_unchanged_source(
            source_path,
            source_root=case_path.parent,
            byte_count=int(source_snapshot["byte_count"]),
            sha256=str(source_snapshot["sha256"]),
        )
        return reconciliation

    scenario_columns = (
        *SCENARIO_FIXED_COLUMNS,
        *dimensions,
        *SCENARIO_METRIC_COLUMNS,
    )
    _write_csv(
        output_paths["sales_plan_scenario"],
        scenario_columns,
        scenario_rows,
    )
    _write_csv(
        output_paths["assumption_application_ledger"],
        LEDGER_COLUMNS,
        ledger_rows,
    )
    _write_csv(
        output_paths["scenario_summary"],
        SUMMARY_COLUMNS,
        summary_rows,
    )
    write_json(output_paths["reconciliation"], reconciliation)
    output_artifacts = [
        _artifact_record(
            "sales_plan_scenario",
            output_paths["sales_plan_scenario"],
            "text/csv",
        ),
        _artifact_record(
            "assumption_application_ledger",
            output_paths["assumption_application_ledger"],
            "text/csv",
        ),
        _artifact_record(
            "scenario_summary",
            output_paths["scenario_summary"],
            "text/csv",
        ),
        _artifact_record(
            "reconciliation",
            output_paths["reconciliation"],
            "application/json",
        ),
    ]
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "case_id": str(case["case_id"]),
        "preparation_status": "passed",
        "report_ready": False,
        "case_contract": {
            "path": case_path.name,
            "sha256": file_sha256(case_path),
        },
        "inputs": [
            {
                "artifact_id": "actual_sales",
                "path": source_path.relative_to(case_path.parent).as_posix(),
                "sha256": str(source_snapshot["sha256"]),
                "size_bytes": int(source_snapshot["byte_count"]),
            }
        ],
        "reviewed_assumptions": {
            "status": "reviewed",
            "assumption_count": len(assumptions),
            "assumption_ids": [
                str(assumption["assumption_id"]) for assumption in assumptions
            ],
            "canonical_sha256": canonical_json_sha256(assumptions),
        },
        "recipe": {
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "engine_path": "scripts/prepare_sales_plan_case.py",
            "engine_sha256": file_sha256(Path(__file__).resolve()),
            "arithmetic": "decimal_exact",
            "time_profile": TIME_PROFILE,
            "fx_rate_definition": FX_RATE_DEFINITION,
            "same_driver_overlap_behavior": str(recipe["same_driver_overlap_behavior"]),
            "discount_assumption_basis": str(recipe["discount_assumption_basis"]),
            "cogs_assumption_basis": str(recipe["cogs_assumption_basis"]),
        },
        "lineage": {
            "grain": "source_row_and_mapped_target_period",
            "source_row_id_column": metrics["source_row_id"],
            "dimension_columns": list(dimensions),
            "period_mapping": list(period_mapping),
            "source_profile": source_profile,
            "assumption_application_ledger": (
                output_paths["assumption_application_ledger"].name
            ),
        },
        "reconciliation": {
            "status": "passed",
            "sha256": file_sha256(output_paths["reconciliation"]),
        },
        "outputs": output_artifacts,
        "canonical_output_set_sha256": canonical_json_sha256(output_artifacts),
        "professional_boundary": {
            "prospective_assumptions_are_not_source_facts": True,
            "professional_approval_required": True,
            "report_ready": False,
        },
    }
    write_json(output_paths["prepared_evidence_manifest"], manifest)
    _require_unchanged_source(
        source_path,
        source_root=case_path.parent,
        byte_count=int(source_snapshot["byte_count"]),
        sha256=str(source_snapshot["sha256"]),
    )
    return reconciliation


def prepare_sales_plan_case(case_path: Path, output_dir: Path) -> dict[str, Any]:
    """Prepare one reviewed sales-plan case and return its reconciliation."""

    with exact_decimal_context(DECIMAL_POLICY):
        return _prepare_sales_plan_case_exact(case_path, output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the sales-plan preparation command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="Path to case.json")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for deterministic preparation outputs",
    )
    args = parser.parse_args(argv)
    try:
        result = prepare_sales_plan_case(args.case, args.output_dir)
    except (ContractValidationError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("FAILED: %s", exc)
        return 2
    LOGGER.info(
        "Sales-plan preparation %s with %s error(s)",
        result["status"],
        result["counts"]["errors"],
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
