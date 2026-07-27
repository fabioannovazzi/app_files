#!/usr/bin/env python3
"""Prepare an exact synthetic monthly P&L against reviewed public controls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
from pathlib import Path
from typing import Any

__all__ = ["main", "prepare_monthly_pnl_case"]

LOGGER = logging.getLogger(__name__)

CASE_SCHEMA = "clara.monthly_pnl_preparation_case.v1"
RECONCILIATION_SCHEMA = "clara.reconciliation_result.v1"
MANIFEST_SCHEMA = "clara.prepared_evidence_manifest.v1"
RECIPE_ID = "monthly_pnl_from_reviewed_mapping.v1"
ENGINE_VERSION = "1.0.0"
SCENARIO = "SYN"

TRIAL_BALANCE_COLUMNS = (
    "source_row_id",
    "scope_id",
    "entity_id",
    "account_code",
    "account_name",
    "period",
    "period_start",
    "period_end",
    "value",
    "currency",
    "unit",
    "source_classification",
)
MAPPING_COLUMNS = (
    "mapping_row_id",
    "mapping_version",
    "scope_id",
    "entity_id",
    "account_code",
    "account_name",
    "mapping_action",
    "statement_line_id",
    "presentation_multiplier",
    "effective_start",
    "effective_end",
    "status",
    "reviewed_on",
    "evidence",
)
PUBLIC_FACT_COLUMNS = (
    "fact_id",
    "row_key",
    "period_start",
    "period_end",
    "period",
    "period_grain",
    "source_value",
    "normalization_multiplier",
    "value",
    "unit",
    "reported_increment",
    "source_id",
    "source_locator",
)
MONTHLY_PNL_COLUMNS = (
    "row_key",
    "period",
    "scenario",
    "value",
    "unit",
    "period_start",
    "period_end",
    "line_type",
    "display_order",
)
UNMAPPED_COLUMNS = (
    "source_row_id",
    "scope_id",
    "entity_id",
    "account_code",
    "account_name",
    "period",
    "period_start",
    "period_end",
    "source_value",
    "unit",
    "reason",
)

STATEMENT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("net_sales", "detail", "001"),
    ("cost_of_products_sold", "detail", "002"),
    ("gross_profit", "subtotal", "003"),
    ("selling_general_and_administrative", "detail", "004"),
    ("advertising_and_sales_promotion", "detail", "005"),
    (
        "amortization_of_definite_lived_intangible_assets",
        "detail",
        "006",
    ),
    ("total_operating_expenses", "subtotal", "007"),
    ("income_from_operations", "subtotal", "008"),
    ("interest_income", "detail", "009"),
    ("interest_expense", "detail", "010"),
    ("other_income_expense_net", "detail", "011"),
    ("income_before_income_taxes", "subtotal", "012"),
    ("provision_for_income_taxes", "detail", "013"),
    ("net_income", "total", "014"),
)
STATEMENT_LINE_IDS = tuple(row[0] for row in STATEMENT_ROWS)
STATEMENT_ROW_META = {
    row_key: {"line_type": line_type, "display_order": display_order}
    for row_key, line_type, display_order in STATEMENT_ROWS
}
LEAF_LINE_IDS = (
    "net_sales",
    "cost_of_products_sold",
    "selling_general_and_administrative",
    "advertising_and_sales_promotion",
    "amortization_of_definite_lived_intangible_assets",
    "interest_income",
    "interest_expense",
    "other_income_expense_net",
    "provision_for_income_taxes",
)
DERIVED_LINE_DEPENDENCIES = {
    "gross_profit": ("net_sales", "cost_of_products_sold"),
    "total_operating_expenses": (
        "selling_general_and_administrative",
        "advertising_and_sales_promotion",
        "amortization_of_definite_lived_intangible_assets",
    ),
    "income_from_operations": (
        "gross_profit",
        "total_operating_expenses",
    ),
    "income_before_income_taxes": (
        "income_from_operations",
        "interest_income",
        "interest_expense",
        "other_income_expense_net",
    ),
    "net_income": (
        "income_before_income_taxes",
        "provision_for_income_taxes",
    ),
}
PRESENTATION_MULTIPLIERS = {
    "net_sales": Decimal("-1"),
    "cost_of_products_sold": Decimal("1"),
    "selling_general_and_administrative": Decimal("1"),
    "advertising_and_sales_promotion": Decimal("1"),
    "amortization_of_definite_lived_intangible_assets": Decimal("1"),
    "interest_income": Decimal("-1"),
    "interest_expense": Decimal("1"),
    "other_income_expense_net": Decimal("-1"),
    "provision_for_income_taxes": Decimal("1"),
}
PUBLIC_NORMALIZATION_MULTIPLIERS = {
    row_key: Decimal("-1") if row_key == "interest_expense" else Decimal("1")
    for row_key in STATEMENT_LINE_IDS
}
NON_NEGATIVE_LINES = frozenset(
    {
        "net_sales",
        "cost_of_products_sold",
        "gross_profit",
        "selling_general_and_administrative",
        "advertising_and_sales_promotion",
        "amortization_of_definite_lived_intangible_assets",
        "total_operating_expenses",
        "income_from_operations",
        "interest_income",
        "interest_expense",
        "income_before_income_taxes",
        "net_income",
    }
)
CHECK_IDS = (
    "input_contract",
    "duplicate_control",
    "period_contract",
    "unit_contract",
    "scope_contract",
    "mapping_contract",
    "source_row_conservation",
    "trial_balance_identity",
    "sign_contract",
    "leaf_aggregation_conservation",
    "monthly_statement_identities",
    "public_tie_outs",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
MAX_INPUT_DECIMAL_DIGITS = 38
MAX_INPUT_DECIMAL_SCALE = 6
CALCULATION_PRECISION = 128


@dataclass(frozen=True)
class PeriodSpec:
    """One reviewed monthly preparation period."""

    period: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class PublicPeriodSpec:
    """One reviewed public comparison period."""

    period: str
    period_grain: str
    period_start: date
    period_end: date
    member_periods: tuple[str, ...]
    source_id: str


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    result = value.strip()
    if not result and not allow_empty:
        raise ValueError(f"{label} must be non-empty text")
    return result


def _iso_date(value: Any, *, label: str) -> date:
    try:
        return date.fromisoformat(_text(value, label=label))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _decimal(value: Any, *, label: str) -> Decimal:
    text = _text(value, label=label)
    if DECIMAL_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical decimal string")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a canonical decimal string") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    parts = result.as_tuple()
    if not isinstance(parts.exponent, int):
        raise ValueError(f"{label} must be finite")
    if len(parts.digits) > MAX_INPUT_DECIMAL_DIGITS:
        raise ValueError(
            f"{label} must contain at most {MAX_INPUT_DECIMAL_DIGITS} digits"
        )
    if max(-parts.exponent, 0) > MAX_INPUT_DECIMAL_SCALE:
        raise ValueError(
            f"{label} must contain at most {MAX_INPUT_DECIMAL_SCALE} decimal places"
        )
    return result


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("output decimal values must be finite")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _case_file(case_root: Path, raw_path: Any, *, label: str) -> Path:
    relative = Path(_text(raw_path, label=label))
    if relative.is_absolute():
        raise ValueError(f"{label} must be relative to the case directory")
    resolved_root = case_root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label} must stay inside the case directory")
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {relative.as_posix()}")
    return resolved


def _read_csv(
    path: Path, *, columns: tuple[str, ...], label: str
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f"{label} columns must equal {list(columns)}")
        for position, raw_row in enumerate(reader, start=2):
            if None in raw_row or any(value is None for value in raw_row.values()):
                raise ValueError(
                    f"{label} row {position} does not match the declared columns"
                )
            rows.append({column: str(raw_row[column]) for column in columns})
    if not rows:
        raise ValueError(f"{label} must contain at least one row")
    return rows


def _write_csv(
    path: Path, columns: tuple[str, ...], rows: Sequence[Mapping[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(columns),
            lineterminator="\n",
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _next_month(period: PeriodSpec) -> date:
    if period.period_end.month == 12:
        return date(period.period_end.year + 1, 1, 1)
    return date(period.period_end.year, period.period_end.month + 1, 1)


def _load_periods(raw_periods: Any) -> tuple[PeriodSpec, ...]:
    periods: list[PeriodSpec] = []
    for position, raw_period in enumerate(
        _sequence(raw_periods, label="preparation_recipe.periods"), start=1
    ):
        record = _mapping(raw_period, label=f"preparation_recipe.periods[{position}]")
        period = _text(
            record.get("period"),
            label=f"preparation_recipe.periods[{position}].period",
        )
        period_start = _iso_date(
            record.get("period_start"),
            label=f"preparation_recipe.periods[{position}].period_start",
        )
        period_end = _iso_date(
            record.get("period_end"),
            label=f"preparation_recipe.periods[{position}].period_end",
        )
        if period != period_start.strftime("%Y-%m"):
            raise ValueError(f"period {period!r} must match its period_start month")
        if (
            period_start.day != 1
            or (period_start.year, period_start.month)
            != (period_end.year, period_end.month)
            or _next_month(PeriodSpec(period, period_start, period_end)) - period_end
            != date.resolution
        ):
            raise ValueError(
                f"period {period!r} must cover one complete calendar month"
            )
        periods.append(PeriodSpec(period, period_start, period_end))
    if len(periods) != 12:
        raise ValueError("registered monthly P&L recipe requires exactly 12 periods")
    if len({period.period for period in periods}) != len(periods):
        raise ValueError("preparation periods must be unique")
    if tuple(sorted(periods, key=lambda item: item.period_start)) != tuple(periods):
        raise ValueError("preparation periods must be ordered")
    for previous, current in zip(periods, periods[1:]):
        if _next_month(previous) != current.period_start:
            raise ValueError("preparation periods must be contiguous calendar months")
    return tuple(periods)


def _load_public_periods(
    raw_periods: Any,
    *,
    monthly_periods: tuple[PeriodSpec, ...],
    source_roles: Mapping[str, str],
) -> tuple[PublicPeriodSpec, ...]:
    monthly_ids = {period.period for period in monthly_periods}
    result: list[PublicPeriodSpec] = []
    for position, raw_period in enumerate(
        _sequence(raw_periods, label="preparation_recipe.public_periods"), start=1
    ):
        record = _mapping(
            raw_period, label=f"preparation_recipe.public_periods[{position}]"
        )
        period = _text(
            record.get("period"),
            label=f"preparation_recipe.public_periods[{position}].period",
        )
        grain = _text(
            record.get("period_grain"),
            label=f"preparation_recipe.public_periods[{position}].period_grain",
        )
        if grain not in {"quarter", "year"}:
            raise ValueError(f"public period {period!r} must be quarter or year")
        member_periods = tuple(
            _text(item, label=f"public period {period}.member_periods[]")
            for item in _sequence(
                record.get("member_periods"),
                label=f"public period {period}.member_periods",
            )
        )
        expected_count = 3 if grain == "quarter" else 12
        if (
            len(member_periods) != expected_count
            or len(set(member_periods)) != expected_count
            or not set(member_periods).issubset(monthly_ids)
        ):
            raise ValueError(
                f"public period {period!r} must reference {expected_count} unique "
                "preparation months"
            )
        period_start = _iso_date(
            record.get("period_start"), label=f"public period {period}.period_start"
        )
        period_end = _iso_date(
            record.get("period_end"), label=f"public period {period}.period_end"
        )
        monthly_index = {item.period: item for item in monthly_periods}
        if (
            period_start != monthly_index[member_periods[0]].period_start
            or period_end != monthly_index[member_periods[-1]].period_end
        ):
            raise ValueError(
                f"public period {period!r} bounds must match its member months"
            )
        source_id = _text(
            record.get("source_id"), label=f"public period {period}.source_id"
        )
        if source_id not in source_roles:
            raise ValueError(
                f"public period {period!r} references unknown source {source_id!r}"
            )
        expected_role = "quarterly_control" if grain == "quarter" else "annual_control"
        if source_roles[source_id] != expected_role:
            raise ValueError(
                f"public period {period!r} must use a {expected_role} source"
            )
        result.append(
            PublicPeriodSpec(
                period=period,
                period_grain=grain,
                period_start=period_start,
                period_end=period_end,
                member_periods=member_periods,
                source_id=source_id,
            )
        )
    if len(result) != 5:
        raise ValueError(
            "registered monthly P&L recipe requires four quarters and one year"
        )
    if len({period.period for period in result}) != len(result):
        raise ValueError("public comparison periods must be unique")
    quarters = [item for item in result if item.period_grain == "quarter"]
    years = [item for item in result if item.period_grain == "year"]
    if len(quarters) != 4 or len(years) != 1:
        raise ValueError(
            "public comparison periods must contain four quarters and one year"
        )
    quarter_members = [
        month for quarter in quarters for month in quarter.member_periods
    ]
    if quarter_members != [period.period for period in monthly_periods]:
        raise ValueError(
            "public quarters must partition the 12 preparation months in order"
        )
    if years[0].member_periods != tuple(period.period for period in monthly_periods):
        raise ValueError(
            "public fiscal year must contain all preparation months in order"
        )
    return tuple(result)


def _load_sources(raw_sources: Any) -> tuple[list[dict[str, Any]], set[str]]:
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    required = {
        "source_id",
        "title",
        "form",
        "accession",
        "filed_date",
        "url",
        "byte_count",
        "sha256",
        "role",
    }
    for position, raw_source in enumerate(
        _sequence(raw_sources, label="case.sources"), start=1
    ):
        source = dict(_mapping(raw_source, label=f"case.sources[{position}]"))
        if set(source) != required:
            raise ValueError(
                f"case.sources[{position}] fields must equal {sorted(required)}"
            )
        source_id = _text(
            source["source_id"], label=f"case.sources[{position}].source_id"
        )
        if source_id in source_ids:
            raise ValueError(f"duplicate source_id {source_id!r}")
        source_ids.add(source_id)
        _text(source["title"], label=f"source {source_id}.title")
        _text(source["form"], label=f"source {source_id}.form")
        _text(source["accession"], label=f"source {source_id}.accession")
        _iso_date(source["filed_date"], label=f"source {source_id}.filed_date")
        url = _text(source["url"], label=f"source {source_id}.url")
        if not url.startswith("https://www.sec.gov/"):
            raise ValueError(f"source {source_id}.url must be an SEC HTTPS URL")
        byte_count = source["byte_count"]
        if type(byte_count) is not int or byte_count <= 0:
            raise ValueError(f"source {source_id}.byte_count must be positive")
        sha256 = _text(source["sha256"], label=f"source {source_id}.sha256")
        if SHA256_PATTERN.fullmatch(sha256) is None:
            raise ValueError(f"source {source_id}.sha256 must be lowercase SHA-256")
        if source["role"] not in {"quarterly_control", "annual_control"}:
            raise ValueError(f"source {source_id}.role is unsupported")
        sources.append(source)
    if not sources:
        raise ValueError("case.sources must not be empty")
    return sources, source_ids


def _load_case(
    case_path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Path],
    tuple[PeriodSpec, ...],
    tuple[PublicPeriodSpec, ...],
    list[dict[str, Any]],
]:
    try:
        raw_case = json.loads(
            case_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("case must contain valid JSON") from exc
    case = dict(_mapping(raw_case, label="case"))
    if case.get("schema_version") != CASE_SCHEMA:
        raise ValueError("unsupported monthly P&L case schema")
    _text(case.get("case_id"), label="case.case_id")
    _text(case.get("purpose"), label="case.purpose")

    sources, _source_ids = _load_sources(case.get("sources"))
    source_roles = {str(source["source_id"]): str(source["role"]) for source in sources}
    recipe = _mapping(case.get("preparation_recipe"), label="preparation_recipe")
    if recipe.get("recipe_id") != RECIPE_ID:
        raise ValueError(f"preparation_recipe.recipe_id must equal {RECIPE_ID!r}")
    if recipe.get("engine_version") != ENGINE_VERSION:
        raise ValueError(
            f"preparation_recipe.engine_version must equal {ENGINE_VERSION!r}"
        )
    if recipe.get("scenario") != SCENARIO:
        raise ValueError(f"preparation_recipe.scenario must equal {SCENARIO!r}")
    if recipe.get("arithmetic") != "decimal_exact":
        raise ValueError("preparation_recipe.arithmetic must equal decimal_exact")
    if recipe.get("trial_balance_sign_convention") != "debit_positive_credit_negative":
        raise ValueError(
            "preparation_recipe.trial_balance_sign_convention must equal "
            "debit_positive_credit_negative"
        )
    expected_signs = {
        "expense_lines": "positive_magnitude",
        "income_lines": "positive_magnitude",
        "interest_expense": "positive_magnitude",
        "other_income_expense_net": "signed_income_positive",
        "provision_for_income_taxes": "signed_expense_positive",
    }
    if recipe.get("statement_sign_convention") != expected_signs:
        raise ValueError(
            "preparation_recipe.statement_sign_convention is not the registered contract"
        )
    _text(recipe.get("currency"), label="preparation_recipe.currency")
    _text(recipe.get("unit"), label="preparation_recipe.unit")
    _text(recipe.get("scope_id"), label="preparation_recipe.scope_id")
    _text(recipe.get("entity_id"), label="preparation_recipe.entity_id")
    periods = _load_periods(recipe.get("periods"))
    public_periods = _load_public_periods(
        recipe.get("public_periods"),
        monthly_periods=periods,
        source_roles=source_roles,
    )

    mapping_contract = _mapping(case.get("reviewed_mapping"), label="reviewed_mapping")
    _text(mapping_contract.get("mapping_id"), label="reviewed_mapping.mapping_id")
    _text(
        mapping_contract.get("mapping_version"),
        label="reviewed_mapping.mapping_version",
    )
    if mapping_contract.get("required_status") != "reviewed":
        raise ValueError("reviewed_mapping.required_status must equal reviewed")
    _text(
        mapping_contract.get("review_basis"),
        label="reviewed_mapping.review_basis",
    )

    relationship = _mapping(
        case.get("reviewed_scope_relationship"),
        label="reviewed_scope_relationship",
    )
    if relationship.get("status") != "reviewed":
        raise ValueError("reviewed_scope_relationship.status must equal reviewed")
    if relationship.get("prepared_scope_id") != recipe.get("scope_id"):
        raise ValueError(
            "reviewed_scope_relationship.prepared_scope_id must match recipe scope"
        )
    _text(
        relationship.get("public_scope_id"),
        label="reviewed_scope_relationship.public_scope_id",
    )
    _text(
        relationship.get("statement"),
        label="reviewed_scope_relationship.statement",
    )

    boundary = _mapping(case.get("disclosure_boundary"), label="disclosure_boundary")
    if boundary.get("monthly_values_are_company_actuals") is not False:
        raise ValueError(
            "disclosure_boundary.monthly_values_are_company_actuals must be false"
        )
    if boundary.get("public_fact_grains") != ["quarter", "year"]:
        raise ValueError(
            "disclosure_boundary.public_fact_grains must equal quarter and year"
        )
    synthetic_elements = {
        _text(item, label="disclosure_boundary.synthetic_elements[]")
        for item in _sequence(
            boundary.get("synthetic_elements"),
            label="disclosure_boundary.synthetic_elements",
        )
    }
    required_synthetic = {
        "monthly_phasing",
        "account_codes",
        "account_names",
        "account_splits",
        "coa_mapping",
        "clearing_account",
    }
    if not required_synthetic.issubset(synthetic_elements):
        raise ValueError(
            "disclosure_boundary.synthetic_elements omits required fixture elements"
        )

    files = _mapping(case.get("files"), label="case.files")
    required_files = {
        "synthetic_monthly_trial_balance",
        "reviewed_coa_mapping",
        "public_statement_facts",
    }
    if set(files) != required_files:
        raise ValueError(f"case.files must equal {sorted(required_files)}")
    case_root = case_path.resolve().parent
    paths: dict[str, Path] = {}
    for file_id in sorted(required_files):
        record = _mapping(files[file_id], label=f"case.files.{file_id}")
        if set(record) != {"path", "sha256"}:
            raise ValueError(
                f"case.files.{file_id} must contain exactly path and sha256"
            )
        path = _case_file(
            case_root, record.get("path"), label=f"case.files.{file_id}.path"
        )
        declared_sha = _text(record.get("sha256"), label=f"case.files.{file_id}.sha256")
        if SHA256_PATTERN.fullmatch(declared_sha) is None:
            raise ValueError(f"case.files.{file_id}.sha256 must be lowercase SHA-256")
        actual_sha = _sha256_file(path)
        if actual_sha != declared_sha:
            raise ValueError(
                f"case.files.{file_id} digest mismatch: "
                f"declared {declared_sha}, actual {actual_sha}"
            )
        paths[file_id] = path
    return case, paths, periods, public_periods, sources


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
            "identifiers": sorted(str(item) for item in identifiers),
        }
    )


def _prepare_mappings(
    rows: Sequence[Mapping[str, str]],
    *,
    case: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    contract = _mapping(case["reviewed_mapping"], label="reviewed_mapping")
    expected_scope = str(recipe["scope_id"])
    expected_entity = str(recipe["entity_id"])
    expected_version = str(contract["mapping_version"])
    expected_status = str(contract["required_status"])
    records_by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mapping_row_ids: set[str] = set()
    leaf_lines_seen: set[str] = set()

    for position, row in enumerate(rows, start=2):
        label = f"reviewed mapping row {position}"
        mapping_row_id = _text(row["mapping_row_id"], label=f"{label}.mapping_row_id")
        account_code = _text(row["account_code"], label=f"{label}.account_code")
        account_name = _text(row["account_name"], label=f"{label}.account_name")
        action = _text(row["mapping_action"], label=f"{label}.mapping_action")
        statement_line_id = _text(
            row["statement_line_id"],
            label=f"{label}.statement_line_id",
            allow_empty=True,
        )
        multiplier_text = _text(
            row["presentation_multiplier"],
            label=f"{label}.presentation_multiplier",
            allow_empty=True,
        )
        effective_start = _iso_date(
            row["effective_start"], label=f"{label}.effective_start"
        )
        effective_end = _iso_date(row["effective_end"], label=f"{label}.effective_end")
        if effective_start > effective_end:
            _add_error(
                errors,
                gate="mapping_contract",
                code="invalid_mapping_effective_range",
                message=f"{mapping_row_id} effective_start follows effective_end",
                identifiers=[mapping_row_id],
            )
        if mapping_row_id in mapping_row_ids:
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_mapping_row_id",
                message=f"duplicate mapping_row_id {mapping_row_id}",
                identifiers=[mapping_row_id],
            )
        mapping_row_ids.add(mapping_row_id)

        if row["mapping_version"] != expected_version:
            _add_error(
                errors,
                gate="mapping_contract",
                code="mapping_version_mismatch",
                message=f"{mapping_row_id} does not use reviewed mapping version",
                identifiers=[mapping_row_id],
            )
        if row["status"] != expected_status:
            _add_error(
                errors,
                gate="mapping_contract",
                code="mapping_status_not_reviewed",
                message=f"{mapping_row_id} is not reviewed",
                identifiers=[mapping_row_id],
            )
        if row["scope_id"] != expected_scope or row["entity_id"] != expected_entity:
            _add_error(
                errors,
                gate="scope_contract",
                code="mapping_scope_mismatch",
                message=f"{mapping_row_id} is outside the reviewed prepared scope",
                identifiers=[mapping_row_id],
            )
        _iso_date(row["reviewed_on"], label=f"{label}.reviewed_on")
        _text(row["evidence"], label=f"{label}.evidence")

        multiplier: Decimal | None = None
        if action == "include":
            if statement_line_id not in LEAF_LINE_IDS:
                _add_error(
                    errors,
                    gate="mapping_contract",
                    code="invalid_mapping_target",
                    message=f"{mapping_row_id} targets an unsupported leaf line",
                    identifiers=[mapping_row_id, statement_line_id],
                )
            else:
                leaf_lines_seen.add(statement_line_id)
            if multiplier_text:
                multiplier = _decimal(
                    multiplier_text, label=f"{label}.presentation_multiplier"
                )
            expected_multiplier = PRESENTATION_MULTIPLIERS.get(statement_line_id)
            if multiplier != expected_multiplier:
                _add_error(
                    errors,
                    gate="sign_contract",
                    code="mapping_sign_mismatch",
                    message=f"{mapping_row_id} violates the reviewed debit-positive sign",
                    identifiers=[mapping_row_id, statement_line_id],
                )
        elif action == "exclude":
            if statement_line_id or multiplier_text:
                _add_error(
                    errors,
                    gate="mapping_contract",
                    code="invalid_reviewed_exclusion",
                    message=(
                        f"{mapping_row_id} exclusion must not carry a target or multiplier"
                    ),
                    identifiers=[mapping_row_id],
                )
        else:
            _add_error(
                errors,
                gate="mapping_contract",
                code="invalid_mapping_action",
                message=f"{mapping_row_id} mapping_action must be include or exclude",
                identifiers=[mapping_row_id],
            )

        records_by_account[account_code].append(
            {
                "mapping_row_id": mapping_row_id,
                "account_code": account_code,
                "account_name": account_name,
                "action": action,
                "statement_line_id": statement_line_id,
                "multiplier": multiplier,
                "effective_start": effective_start,
                "effective_end": effective_end,
                "scope_id": row["scope_id"],
                "entity_id": row["entity_id"],
            }
        )

    for missing_line in sorted(set(LEAF_LINE_IDS) - leaf_lines_seen):
        _add_error(
            errors,
            gate="mapping_contract",
            code="missing_leaf_mapping",
            message=f"no reviewed mapping targets {missing_line}",
            identifiers=[missing_line],
        )
    return dict(records_by_account), mapping_row_ids


def _derive_statement(leaf_values: Mapping[str, Decimal]) -> dict[str, Decimal]:
    values = {
        line_id: leaf_values.get(line_id, Decimal(0)) for line_id in LEAF_LINE_IDS
    }
    values["gross_profit"] = values["net_sales"] - values["cost_of_products_sold"]
    values["total_operating_expenses"] = (
        values["selling_general_and_administrative"]
        + values["advertising_and_sales_promotion"]
        + values["amortization_of_definite_lived_intangible_assets"]
    )
    values["income_from_operations"] = (
        values["gross_profit"] - values["total_operating_expenses"]
    )
    values["income_before_income_taxes"] = (
        values["income_from_operations"]
        + values["interest_income"]
        - values["interest_expense"]
        + values["other_income_expense_net"]
    )
    values["net_income"] = (
        values["income_before_income_taxes"] - values["provision_for_income_taxes"]
    )
    return values


def _identity_differences(values: Mapping[str, Decimal]) -> dict[str, Decimal]:
    return {
        "gross_profit": values["gross_profit"]
        - (values["net_sales"] - values["cost_of_products_sold"]),
        "total_operating_expenses": values["total_operating_expenses"]
        - (
            values["selling_general_and_administrative"]
            + values["advertising_and_sales_promotion"]
            + values["amortization_of_definite_lived_intangible_assets"]
        ),
        "income_from_operations": values["income_from_operations"]
        - (values["gross_profit"] - values["total_operating_expenses"]),
        "income_before_income_taxes": values["income_before_income_taxes"]
        - (
            values["income_from_operations"]
            + values["interest_income"]
            - values["interest_expense"]
            + values["other_income_expense_net"]
        ),
        "net_income": values["net_income"]
        - (values["income_before_income_taxes"] - values["provision_for_income_taxes"]),
    }


def _prepare_trial_balance(
    rows: Sequence[Mapping[str, str]],
    *,
    case: Mapping[str, Any],
    periods: tuple[PeriodSpec, ...],
    mappings_by_account: Mapping[str, Sequence[Mapping[str, Any]]],
    errors: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Decimal]],
    list[dict[str, str]],
    dict[str, Any],
    dict[str, list[str]],
    list[dict[str, Any]],
]:
    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    expected_scope = str(recipe["scope_id"])
    expected_entity = str(recipe["entity_id"])
    expected_currency = str(recipe["currency"])
    expected_unit = str(recipe["unit"])
    period_by_id = {period.period: period for period in periods}

    source_row_counts: Counter[str] = Counter()
    natural_key_counts: Counter[tuple[str, str, str, str]] = Counter()
    account_period_counts: Counter[tuple[str, str]] = Counter()
    account_names: dict[str, str] = {}
    seen_mapping_row_ids: set[str] = set()
    included_rows = 0
    excluded_rows = 0
    unresolved_rows = 0
    fanout_rows = 0
    period_balances: dict[str, Decimal] = defaultdict(Decimal)
    included_source_row_ids: list[str] = []
    leaf_contributions: dict[tuple[str, str], list[tuple[str, Decimal]]] = defaultdict(
        list
    )
    unmapped_rows: list[dict[str, str]] = []
    base_line_accounts: dict[str, set[str]] = defaultdict(set)

    for position, row in enumerate(rows, start=2):
        label = f"trial balance row {position}"
        source_row_id = _text(row["source_row_id"], label=f"{label}.source_row_id")
        account_code = _text(row["account_code"], label=f"{label}.account_code")
        account_name = _text(row["account_name"], label=f"{label}.account_name")
        period_id = _text(row["period"], label=f"{label}.period")
        period_start = _iso_date(row["period_start"], label=f"{label}.period_start")
        period_end = _iso_date(row["period_end"], label=f"{label}.period_end")
        value = _decimal(row["value"], label=f"{label}.value")

        source_row_counts[source_row_id] += 1
        natural_key_counts[
            (row["scope_id"], row["entity_id"], account_code, period_id)
        ] += 1
        account_period_counts[(account_code, period_id)] += 1
        if (
            account_code in account_names
            and account_names[account_code] != account_name
        ):
            _add_error(
                errors,
                gate="mapping_contract",
                code="inconsistent_account_name",
                message=f"{account_code} has multiple account names",
                identifiers=[account_code],
            )
        account_names.setdefault(account_code, account_name)

        period = period_by_id.get(period_id)
        if period is None:
            _add_error(
                errors,
                gate="period_contract",
                code="unexpected_period",
                message=f"{source_row_id} uses unexpected period {period_id}",
                identifiers=[source_row_id, period_id],
            )
        elif period_start != period.period_start or period_end != period.period_end:
            _add_error(
                errors,
                gate="period_contract",
                code="period_bounds_mismatch",
                message=f"{source_row_id} does not use the reviewed month bounds",
                identifiers=[source_row_id, period_id],
            )

        if row["scope_id"] != expected_scope or row["entity_id"] != expected_entity:
            _add_error(
                errors,
                gate="scope_contract",
                code="trial_balance_scope_mismatch",
                message=f"{source_row_id} is outside the reviewed prepared scope",
                identifiers=[source_row_id],
            )
        if row["currency"] != expected_currency:
            _add_error(
                errors,
                gate="unit_contract",
                code="currency_mismatch",
                message=f"{source_row_id} does not use {expected_currency}",
                identifiers=[source_row_id],
            )
        if row["unit"] != expected_unit:
            _add_error(
                errors,
                gate="unit_contract",
                code="unit_mismatch",
                message=f"{source_row_id} does not use {expected_unit}",
                identifiers=[source_row_id],
            )
        if row["source_classification"] != "synthetic":
            _add_error(
                errors,
                gate="input_contract",
                code="invalid_source_classification",
                message=f"{source_row_id} must be explicitly classified synthetic",
                identifiers=[source_row_id],
            )

        if period is not None:
            period_balances[period_id] += value

        candidates = list(mappings_by_account.get(account_code, ()))
        if not candidates:
            unresolved_rows += 1
            unmapped_rows.append(
                {
                    "source_row_id": source_row_id,
                    "scope_id": row["scope_id"],
                    "entity_id": row["entity_id"],
                    "account_code": account_code,
                    "account_name": account_name,
                    "period": period_id,
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "source_value": row["value"],
                    "unit": row["unit"],
                    "reason": "account_absent_from_reviewed_mapping",
                }
            )
            _add_error(
                errors,
                gate="mapping_contract",
                code="unmapped_account",
                message=f"{source_row_id} has no reviewed account mapping",
                identifiers=[source_row_id, account_code],
            )
            continue

        active = [
            candidate
            for candidate in candidates
            if candidate["effective_start"] <= period_start
            and candidate["effective_end"] >= period_end
        ]
        if not active:
            unresolved_rows += 1
            unmapped_rows.append(
                {
                    "source_row_id": source_row_id,
                    "scope_id": row["scope_id"],
                    "entity_id": row["entity_id"],
                    "account_code": account_code,
                    "account_name": account_name,
                    "period": period_id,
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "source_value": row["value"],
                    "unit": row["unit"],
                    "reason": "no_effective_reviewed_mapping",
                }
            )
            _add_error(
                errors,
                gate="mapping_contract",
                code="mapping_effective_gap",
                message=f"{source_row_id} has no mapping effective for its period",
                identifiers=[source_row_id, account_code],
            )
            continue
        if len(active) > 1:
            fanout_rows += 1
            _add_error(
                errors,
                gate="mapping_contract",
                code="mapping_fanout",
                message=f"{source_row_id} has multiple active reviewed mappings",
                identifiers=[
                    source_row_id,
                    *[str(candidate["mapping_row_id"]) for candidate in active],
                ],
            )
            continue

        mapping = active[0]
        seen_mapping_row_ids.add(str(mapping["mapping_row_id"]))
        if mapping["account_name"] != account_name:
            _add_error(
                errors,
                gate="mapping_contract",
                code="mapping_account_name_mismatch",
                message=f"{source_row_id} account name differs from reviewed mapping",
                identifiers=[source_row_id, account_code],
            )
        if (
            mapping["scope_id"] != row["scope_id"]
            or mapping["entity_id"] != row["entity_id"]
        ):
            _add_error(
                errors,
                gate="scope_contract",
                code="mapping_source_scope_mismatch",
                message=f"{source_row_id} and its mapping use different scope",
                identifiers=[source_row_id, str(mapping["mapping_row_id"])],
            )
        if mapping["action"] == "exclude":
            excluded_rows += 1
            continue
        if (
            mapping["action"] != "include"
            or mapping["multiplier"] is None
            or mapping["statement_line_id"] not in LEAF_LINE_IDS
        ):
            unresolved_rows += 1
            continue
        included_rows += 1
        included_source_row_ids.append(source_row_id)
        if period is None:
            continue
        statement_line_id = str(mapping["statement_line_id"])
        normalized = value * mapping["multiplier"]
        leaf_contributions[(period_id, statement_line_id)].append(
            (source_row_id, normalized)
        )
        base_line_accounts[statement_line_id].add(account_code)

    for duplicate_id, count in sorted(source_row_counts.items()):
        if count > 1:
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_source_row_id",
                message=f"source_row_id {duplicate_id} occurs {count} times",
                identifiers=[duplicate_id],
            )
    for natural_key, count in sorted(natural_key_counts.items()):
        if count > 1:
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_trial_balance_natural_key",
                message=f"trial balance natural key occurs {count} times",
                identifiers=list(natural_key),
            )

    expected_account_codes = set(mappings_by_account)
    actual_account_codes = set(account_names)
    for account_code in sorted(expected_account_codes):
        for period in periods:
            count = account_period_counts[(account_code, period.period)]
            if count != 1:
                _add_error(
                    errors,
                    gate="period_contract",
                    code="account_period_coverage",
                    message=(
                        f"{account_code} has {count} rows for expected period "
                        f"{period.period}"
                    ),
                    identifiers=[account_code, period.period],
                )
    for account_code in sorted(expected_account_codes - actual_account_codes):
        _add_error(
            errors,
            gate="mapping_contract",
            code="unused_mapping_account",
            message=f"reviewed account {account_code} is absent from trial balance",
            identifiers=[account_code],
        )

    for period in periods:
        balance = period_balances[period.period]
        if balance != 0:
            _add_error(
                errors,
                gate="trial_balance_identity",
                code="trial_balance_not_zero",
                message=f"{period.period} debit-positive balance is not zero",
                identifiers=[period.period, _decimal_text(balance)],
            )

    leaf_values: dict[str, dict[str, Decimal]] = {
        period.period: {line_id: Decimal(0) for line_id in LEAF_LINE_IDS}
        for period in periods
    }
    contribution_source_row_ids = [
        source_row_id
        for contributions in leaf_contributions.values()
        for source_row_id, _value in contributions
    ]
    if Counter(included_source_row_ids) != Counter(contribution_source_row_ids):
        _add_error(
            errors,
            gate="leaf_aggregation_conservation",
            code="leaf_source_row_multiset_difference",
            message=(
                "included source-row occurrences and leaf contributions do not match"
            ),
            identifiers=[
                f"included={len(included_source_row_ids)}",
                f"contributed={len(contribution_source_row_ids)}",
            ],
        )

    leaf_conservation_results: list[dict[str, Any]] = []
    for period in periods:
        for line_id in LEAF_LINE_IDS:
            contributions = leaf_contributions[(period.period, line_id)]
            contribution_ids = sorted(item[0] for item in contributions)
            input_value = sum((item[1] for item in contributions), Decimal(0))
            leaf_values[period.period][line_id] = input_value
            output_value = leaf_values[period.period][line_id]
            difference = output_value - input_value
            status = "passed" if difference == 0 else "failed"
            leaf_conservation_results.append(
                {
                    "period": period.period,
                    "row_key": line_id,
                    "source_row_count": len(contribution_ids),
                    "source_row_ids_sha256": _canonical_json_sha256(contribution_ids),
                    "mapped_source_value": _decimal_text(input_value),
                    "prepared_leaf_value": _decimal_text(output_value),
                    "difference": _decimal_text(difference),
                    "status": status,
                }
            )
            if difference != 0:
                _add_error(
                    errors,
                    gate="leaf_aggregation_conservation",
                    code="leaf_aggregation_difference",
                    message=f"{period.period} {line_id} does not conserve mapped input",
                    identifiers=[period.period, line_id],
                )

    classified_rows = included_rows + excluded_rows
    if classified_rows != len(rows) or unresolved_rows or fanout_rows:
        _add_error(
            errors,
            gate="source_row_conservation",
            code="source_row_classification_not_conserved",
            message="every source row must resolve to exactly one include or exclusion",
            identifiers=[
                f"input={len(rows)}",
                f"classified={classified_rows}",
                f"unresolved={unresolved_rows}",
                f"fanout={fanout_rows}",
            ],
        )

    diagnostics = {
        "source_rows": len(rows),
        "unique_source_row_ids": len(source_row_counts),
        "mapped_included_rows": included_rows,
        "reviewed_excluded_rows": excluded_rows,
        "unresolved_rows": unresolved_rows,
        "mapping_fanout_rows": fanout_rows,
        "mapping_rows_used": len(seen_mapping_row_ids),
        "trial_balance_accounts": len(actual_account_codes),
    }
    account_lineage = {
        line_id: sorted(base_line_accounts.get(line_id, set()))
        for line_id in LEAF_LINE_IDS
    }
    return (
        leaf_values,
        unmapped_rows,
        diagnostics,
        account_lineage,
        leaf_conservation_results,
    )


def _prepare_monthly_rows(
    leaf_values: Mapping[str, Mapping[str, Decimal]],
    *,
    periods: tuple[PeriodSpec, ...],
    unit: str,
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, dict[str, Decimal]], list[dict[str, str]]]:
    output_rows: list[dict[str, str]] = []
    statement_by_period: dict[str, dict[str, Decimal]] = {}
    identity_results: list[dict[str, str]] = []

    for period in periods:
        values = _derive_statement(leaf_values.get(period.period, {}))
        statement_by_period[period.period] = values
        for line_id in sorted(NON_NEGATIVE_LINES):
            if values[line_id] < 0:
                _add_error(
                    errors,
                    gate="sign_contract",
                    code="normalized_sign_violation",
                    message=f"{period.period} {line_id} is negative",
                    identifiers=[period.period, line_id],
                )
        for identity_id, difference in _identity_differences(values).items():
            status = "passed" if difference == 0 else "failed"
            identity_results.append(
                {
                    "period": period.period,
                    "identity_id": identity_id,
                    "difference": _decimal_text(difference),
                    "status": status,
                }
            )
            if difference != 0:
                _add_error(
                    errors,
                    gate="monthly_statement_identities",
                    code="monthly_statement_identity_failed",
                    message=f"{period.period} {identity_id} identity failed",
                    identifiers=[period.period, identity_id],
                )
        for row_key, line_type, display_order in STATEMENT_ROWS:
            output_rows.append(
                {
                    "row_key": row_key,
                    "period": period.period,
                    "scenario": SCENARIO,
                    "value": _decimal_text(values[row_key]),
                    "unit": unit,
                    "period_start": period.period_start.isoformat(),
                    "period_end": period.period_end.isoformat(),
                    "line_type": line_type,
                    "display_order": display_order,
                }
            )
    output_rows.sort(key=lambda row: (row["display_order"], row["period"]))
    return output_rows, statement_by_period, identity_results


def _prepare_public_facts(
    rows: Sequence[Mapping[str, str]],
    *,
    case: Mapping[str, Any],
    public_periods: tuple[PublicPeriodSpec, ...],
    source_ids: set[str],
    errors: list[dict[str, Any]],
) -> dict[tuple[str, str], Decimal]:
    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    relationship = _mapping(
        case["reviewed_scope_relationship"], label="reviewed_scope_relationship"
    )
    expected_unit = str(recipe["unit"])
    public_scope_id = str(relationship["public_scope_id"])
    period_by_id = {period.period: period for period in public_periods}
    facts: dict[tuple[str, str], Decimal] = {}
    fact_ids: set[str] = set()

    for position, row in enumerate(rows, start=2):
        label = f"public statement fact row {position}"
        fact_id = _text(row["fact_id"], label=f"{label}.fact_id")
        row_key = _text(row["row_key"], label=f"{label}.row_key")
        period_id = _text(row["period"], label=f"{label}.period")
        if fact_id in fact_ids:
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_public_fact_id",
                message=f"duplicate public fact_id {fact_id}",
                identifiers=[fact_id],
            )
        fact_ids.add(fact_id)
        if row_key not in STATEMENT_LINE_IDS:
            _add_error(
                errors,
                gate="public_tie_outs",
                code="unexpected_public_statement_line",
                message=f"{fact_id} uses unsupported statement line {row_key}",
                identifiers=[fact_id, row_key],
            )
            continue
        public_period = period_by_id.get(period_id)
        if public_period is None:
            _add_error(
                errors,
                gate="public_tie_outs",
                code="unexpected_public_period",
                message=f"{fact_id} uses unsupported public period {period_id}",
                identifiers=[fact_id, period_id],
            )
            continue
        if (
            row["period_grain"] != public_period.period_grain
            or row["period_start"] != public_period.period_start.isoformat()
            or row["period_end"] != public_period.period_end.isoformat()
        ):
            _add_error(
                errors,
                gate="period_contract",
                code="public_period_contract_mismatch",
                message=f"{fact_id} does not match its reviewed public period",
                identifiers=[fact_id, period_id],
            )
        if row["unit"] != expected_unit:
            _add_error(
                errors,
                gate="unit_contract",
                code="public_fact_unit_mismatch",
                message=f"{fact_id} does not use {expected_unit}",
                identifiers=[fact_id],
            )
        if row["source_id"] not in source_ids:
            _add_error(
                errors,
                gate="public_tie_outs",
                code="unknown_public_source",
                message=f"{fact_id} references an unknown source",
                identifiers=[fact_id, row["source_id"]],
            )
        if row["source_id"] != public_period.source_id:
            _add_error(
                errors,
                gate="public_tie_outs",
                code="public_period_source_mismatch",
                message=f"{fact_id} does not use the reviewed period source",
                identifiers=[fact_id, row["source_id"]],
            )
        _text(row["source_locator"], label=f"{label}.source_locator")
        reported_increment = _decimal(
            row["reported_increment"], label=f"{label}.reported_increment"
        )
        if reported_increment <= 0:
            raise ValueError(f"{label}.reported_increment must be positive")
        source_value = _decimal(row["source_value"], label=f"{label}.source_value")
        multiplier = _decimal(
            row["normalization_multiplier"],
            label=f"{label}.normalization_multiplier",
        )
        value = _decimal(row["value"], label=f"{label}.value")
        expected_multiplier = PUBLIC_NORMALIZATION_MULTIPLIERS[row_key]
        if source_value % reported_increment != 0 or value % reported_increment != 0:
            _add_error(
                errors,
                gate="public_tie_outs",
                code="public_fact_increment_mismatch",
                message=f"{fact_id} is not on its disclosed reporting increment",
                identifiers=[fact_id, _decimal_text(reported_increment)],
            )
        if multiplier != expected_multiplier:
            _add_error(
                errors,
                gate="sign_contract",
                code="public_normalization_sign_mismatch",
                message=f"{fact_id} violates the registered public sign normalization",
                identifiers=[fact_id, row_key],
            )
        if source_value * multiplier != value:
            _add_error(
                errors,
                gate="public_tie_outs",
                code="public_fact_normalization_failed",
                message=f"{fact_id} normalized value does not equal source value",
                identifiers=[fact_id],
            )
        key = (period_id, row_key)
        if key in facts:
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_public_fact_natural_key",
                message=f"multiple public facts resolve to {period_id} {row_key}",
                identifiers=[period_id, row_key],
            )
        else:
            facts[key] = value

    expected_keys = {
        (period.period, row_key)
        for period in public_periods
        for row_key in STATEMENT_LINE_IDS
    }
    missing = sorted(expected_keys - set(facts))
    unexpected = sorted(set(facts) - expected_keys)
    for period_id, row_key in missing:
        _add_error(
            errors,
            gate="public_tie_outs",
            code="missing_public_fact",
            message=f"missing public fact for {period_id} {row_key}",
            identifiers=[period_id, row_key],
        )
    for period_id, row_key in unexpected:
        _add_error(
            errors,
            gate="public_tie_outs",
            code="unexpected_public_fact",
            message=f"unexpected public fact for {period_id} {row_key}",
            identifiers=[period_id, row_key],
        )
    if public_scope_id != "wd40_company_consolidated":
        _add_error(
            errors,
            gate="scope_contract",
            code="public_scope_contract_changed",
            message="public comparison scope differs from the reviewed case scope",
            identifiers=[public_scope_id],
        )
    return facts


def _public_tie_out_results(
    statement_by_period: Mapping[str, Mapping[str, Decimal]],
    public_facts: Mapping[tuple[str, str], Decimal],
    *,
    public_periods: tuple[PublicPeriodSpec, ...],
    errors: list[dict[str, Any]],
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for public_period in public_periods:
        for row_key in STATEMENT_LINE_IDS:
            prepared_value = sum(
                (
                    statement_by_period.get(month, {}).get(row_key, Decimal(0))
                    for month in public_period.member_periods
                ),
                Decimal(0),
            )
            public_value = public_facts.get((public_period.period, row_key))
            if public_value is None:
                continue
            difference = prepared_value - public_value
            status = "passed" if difference == 0 else "failed"
            results.append(
                {
                    "period": public_period.period,
                    "period_grain": public_period.period_grain,
                    "row_key": row_key,
                    "prepared_value": _decimal_text(prepared_value),
                    "public_value": _decimal_text(public_value),
                    "difference": _decimal_text(difference),
                    "tolerance": "0",
                    "status": status,
                }
            )
            if difference != 0:
                _add_error(
                    errors,
                    gate="public_tie_outs",
                    code="public_anchor_mismatch",
                    message=f"{public_period.period} {row_key} does not tie exactly",
                    identifiers=[public_period.period, row_key],
                )
    return results


def _checks(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    failure_counts = Counter(str(error["gate"]) for error in errors)
    return [
        {
            "check_id": check_id,
            "status": "failed" if failure_counts[check_id] else "passed",
            "failure_count": failure_counts[check_id],
        }
        for check_id in CHECK_IDS
    ]


def _artifact_record(artifact_id: str, path: Path, media_type: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path.name,
        "media_type": media_type,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _prepare_monthly_pnl_case_exact(
    case_path: Path, output_dir: Path
) -> dict[str, Any]:
    """Prepare one case inside the controlled exact-arithmetic context."""

    case_path = Path(case_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "monthly_pnl": output_dir / "monthly_pnl.csv",
        "unmapped_accounts": output_dir / "unmapped_accounts.csv",
        "reconciliation": output_dir / "reconciliation.json",
        "prepared_evidence_manifest": output_dir / "prepared_evidence_manifest.json",
    }
    for path in output_paths.values():
        path.unlink(missing_ok=True)

    case, paths, periods, public_periods, sources = _load_case(case_path)
    trial_balance_rows = _read_csv(
        paths["synthetic_monthly_trial_balance"],
        columns=TRIAL_BALANCE_COLUMNS,
        label="synthetic monthly trial balance",
    )
    mapping_rows = _read_csv(
        paths["reviewed_coa_mapping"],
        columns=MAPPING_COLUMNS,
        label="reviewed COA mapping",
    )
    public_fact_rows = _read_csv(
        paths["public_statement_facts"],
        columns=PUBLIC_FACT_COLUMNS,
        label="public statement facts",
    )

    errors: list[dict[str, Any]] = []
    mappings_by_account, mapping_row_ids = _prepare_mappings(
        mapping_rows, case=case, errors=errors
    )
    (
        leaf_values,
        unmapped_rows,
        source_diagnostics,
        account_lineage,
        leaf_conservation_results,
    ) = _prepare_trial_balance(
        trial_balance_rows,
        case=case,
        periods=periods,
        mappings_by_account=mappings_by_account,
        errors=errors,
    )
    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    monthly_rows, statement_by_period, identity_results = _prepare_monthly_rows(
        leaf_values,
        periods=periods,
        unit=str(recipe["unit"]),
        errors=errors,
    )
    public_facts = _prepare_public_facts(
        public_fact_rows,
        case=case,
        public_periods=public_periods,
        source_ids={str(source["source_id"]) for source in sources},
        errors=errors,
    )
    public_results = _public_tie_out_results(
        statement_by_period,
        public_facts,
        public_periods=public_periods,
        errors=errors,
    )

    errors.sort(
        key=lambda item: (
            str(item["gate"]),
            str(item["code"]),
            str(item["message"]),
            json.dumps(item["identifiers"], sort_keys=True),
        )
    )
    _write_csv(output_paths["unmapped_accounts"], UNMAPPED_COLUMNS, unmapped_rows)

    status = "passed" if not errors else "failed"
    reconciliation: dict[str, Any] = {
        "schema_version": RECONCILIATION_SCHEMA,
        "case_id": str(case["case_id"]),
        "recipe": {
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "arithmetic": "decimal_exact",
        },
        "scope": {
            "prepared_scope_id": str(recipe["scope_id"]),
            "entity_id": str(recipe["entity_id"]),
            "currency": str(recipe["currency"]),
            "unit": str(recipe["unit"]),
            "scenario": SCENARIO,
        },
        "status": status,
        "publication_status": "synthetic_benchmark_only",
        "counts": {
            **source_diagnostics,
            "mapping_rows": len(mapping_rows),
            "mapping_row_ids": len(mapping_row_ids),
            "monthly_periods": len(periods),
            "statement_lines": len(STATEMENT_LINE_IDS),
            "monthly_pnl_rows": len(monthly_rows),
            "monthly_identity_results": len(identity_results),
            "leaf_conservation_results": len(leaf_conservation_results),
            "public_tie_out_results": len(public_results),
            "unmapped_rows": len(unmapped_rows),
            "errors": len(errors),
        },
        "checks": _checks(errors),
        "source_row_conservation": {
            "input_rows": source_diagnostics["source_rows"],
            "classified_rows": (
                source_diagnostics["mapped_included_rows"]
                + source_diagnostics["reviewed_excluded_rows"]
            ),
            "unresolved_rows": source_diagnostics["unresolved_rows"],
            "mapping_fanout_rows": source_diagnostics["mapping_fanout_rows"],
            "status": (
                "passed"
                if (
                    source_diagnostics["source_rows"]
                    == source_diagnostics["mapped_included_rows"]
                    + source_diagnostics["reviewed_excluded_rows"]
                    and source_diagnostics["unresolved_rows"] == 0
                    and source_diagnostics["mapping_fanout_rows"] == 0
                )
                else "failed"
            ),
        },
        "monthly_trial_balance": [
            {
                "period": period.period,
                "difference": _decimal_text(
                    sum(
                        (
                            _decimal(row["value"], label="trial balance output value")
                            for row in trial_balance_rows
                            if row["period"] == period.period
                        ),
                        Decimal(0),
                    )
                ),
                "status": (
                    "passed"
                    if sum(
                        (
                            _decimal(row["value"], label="trial balance output value")
                            for row in trial_balance_rows
                            if row["period"] == period.period
                        ),
                        Decimal(0),
                    )
                    == 0
                    else "failed"
                ),
            }
            for period in periods
        ],
        "leaf_aggregation_conservation": leaf_conservation_results,
        "monthly_statement_identities": identity_results,
        "public_tie_outs": public_results,
        "errors": errors,
        "warnings": [
            {
                "code": "synthetic_monthly_values",
                "message": (
                    "All monthly values, account codes, account splits, and mappings "
                    "are synthetic; only quarter and fiscal-year controls are published."
                ),
            }
        ],
        "downstream_readiness": {
            "status": "not_assessed",
            "report_ready": False,
            "semantic_compatibility": "not_assessed",
            "render_compatibility": "not_assessed",
            "evidence_sealing": "not_assessed",
        },
    }
    _write_json(output_paths["reconciliation"], reconciliation)

    if errors:
        return reconciliation

    _write_csv(output_paths["monthly_pnl"], MONTHLY_PNL_COLUMNS, monthly_rows)
    output_artifacts = [
        _artifact_record("monthly_pnl", output_paths["monthly_pnl"], "text/csv"),
        _artifact_record(
            "unmapped_accounts", output_paths["unmapped_accounts"], "text/csv"
        ),
        _artifact_record(
            "reconciliation",
            output_paths["reconciliation"],
            "application/json",
        ),
    ]
    engine_path = Path(__file__).resolve()
    mapping_contract = _mapping(case["reviewed_mapping"], label="reviewed_mapping")
    boundary = _mapping(case["disclosure_boundary"], label="disclosure_boundary")
    relationship = _mapping(
        case["reviewed_scope_relationship"], label="reviewed_scope_relationship"
    )
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "case_id": str(case["case_id"]),
        "preparation_status": "passed",
        "publication_status": "synthetic_benchmark_only",
        "case_contract": {
            "path": case_path.name,
            "sha256": _sha256_file(case_path),
        },
        "inputs": [
            {
                "artifact_id": file_id,
                "path": paths[file_id].name,
                "sha256": _sha256_file(paths[file_id]),
                "size_bytes": paths[file_id].stat().st_size,
            }
            for file_id in sorted(paths)
        ],
        "reviewed_mapping": {
            "mapping_id": str(mapping_contract["mapping_id"]),
            "mapping_version": str(mapping_contract["mapping_version"]),
            "required_status": str(mapping_contract["required_status"]),
            "sha256": _sha256_file(paths["reviewed_coa_mapping"]),
        },
        "reviewed_scope_relationship": {
            "prepared_scope_id": str(relationship["prepared_scope_id"]),
            "public_scope_id": str(relationship["public_scope_id"]),
            "status": str(relationship["status"]),
        },
        "recipe": {
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "engine_path": "scripts/prepare_monthly_pnl_case.py",
            "engine_sha256": _sha256_file(engine_path),
            "arithmetic": "decimal_exact",
        },
        "lineage": {
            "grain": "statement_line_and_period",
            "base_statement_line_accounts": account_lineage,
            "derived_statement_line_dependencies": {
                key: list(value) for key, value in DERIVED_LINE_DEPENDENCIES.items()
            },
        },
        "source_receipts": sources,
        "disclosure_boundary": {
            "monthly_values_are_company_actuals": False,
            "public_fact_grains": list(boundary["public_fact_grains"]),
            "synthetic_elements": list(boundary["synthetic_elements"]),
        },
        "reconciliation": {
            "status": "passed",
            "sha256": _sha256_file(output_paths["reconciliation"]),
        },
        "outputs": output_artifacts,
        "canonical_output_set_sha256": _canonical_json_sha256(output_artifacts),
        "downstream_readiness": {
            "status": "not_assessed",
            "report_ready": False,
            "semantic_compatibility": "not_assessed",
            "render_compatibility": "not_assessed",
            "evidence_sealing": "not_assessed",
        },
    }
    _write_json(output_paths["prepared_evidence_manifest"], manifest)
    return reconciliation


def prepare_monthly_pnl_case(case_path: Path, output_dir: Path) -> dict[str, Any]:
    """Prepare one frozen monthly P&L case and return its reconciliation payload."""

    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        return _prepare_monthly_pnl_case_exact(case_path, output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the monthly P&L preparation command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="Path to case.json")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for deterministic preparation outputs",
    )
    args = parser.parse_args(argv)
    result = prepare_monthly_pnl_case(args.case, args.output_dir)
    LOGGER.info(
        "Monthly P&L preparation %s with %s error(s)",
        result["status"],
        result["counts"]["errors"],
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
