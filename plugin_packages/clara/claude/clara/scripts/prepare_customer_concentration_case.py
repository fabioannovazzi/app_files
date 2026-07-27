#!/usr/bin/env python3
"""Prepare an exact customer-concentration summary from reviewed filing facts."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    canonical_json_sha256,
    file_sha256,
    read_exact_csv,
    resolve_local_file,
    strict_json_load,
    write_json,
)

__all__ = ["main", "prepare_customer_concentration_case"]

LOGGER = logging.getLogger(__name__)

CASE_SCHEMA = "clara.customer_concentration_preparation_case.v1"
RECONCILIATION_SCHEMA = "clara.customer_concentration_reconciliation.v1"
MANIFEST_SCHEMA = "clara.prepared_evidence_manifest.v1"
RECIPE_ID = "customer_concentration_from_reviewed_public_disclosure.v1"
ENGINE_VERSION = "1.0.0"

CUSTOMER_ALIASES = ("A", "B", "C")
FISCAL_YEARS = ("2025", "2024", "2023")
METRIC_IDS = ("revenue_share", "accounts_receivable")
ALLOWED_OUTPUT_METRIC_IDS = (
    "total_revenue_control",
    "total_accounts_receivable_control",
    "disclosed_top_three_revenue_share",
    "disclosed_accounts_receivable_subtotal",
    "accounts_receivable_coverage_percent",
    "reported_share_hhi_contribution",
)
FORBIDDEN_CLAIM_IDS = (
    "alias_to_customer_name_mapping",
    "precise_customer_revenue_dollars",
    "full_hhi",
    "hhi_lower_bound",
    "monthly_customer_concentration",
    "quarterly_customer_concentration",
    "customer_churn",
    "customer_retention",
)
FACT_COLUMNS = (
    "fact_id",
    "customer_alias",
    "fiscal_year",
    "metric_id",
    "value",
    "unit",
    "reported_increment",
    "source_id",
    "source_locator",
)
CONTROL_FACT_COLUMNS = (
    "control_id",
    "fiscal_year",
    "metric_id",
    "value",
    "unit",
    "reported_increment",
    "source_id",
    "source_locator",
)
SUMMARY_COLUMNS = (
    "summary_id",
    "fiscal_year",
    "metric_id",
    "value",
    "unit",
    "reported_increment",
    "declared_scale",
    "availability_status",
    "characterization",
)
EXCEPTION_COLUMNS = (
    "error_id",
    "gate",
    "code",
    "message",
    "identifiers",
)
CHECK_IDS = (
    "input_contract",
    "exact_fact_set",
    "duplicate_control",
    "alias_period_metric_contract",
    "unit_increment_contract",
    "source_contract",
    "control_values",
    "revenue_share_subtotals",
    "accounts_receivable_subtotals",
    "accounts_receivable_coverage",
    "reported_share_hhi_contribution",
    "claim_abstention",
)
PRODUCER_OUTPUT_NAMES = (
    "customer_concentration_summary.csv",
    "exceptions.csv",
    "prepared_evidence_manifest.json",
    "reconciliation.json",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
INTEGER_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$")


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractValidationError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be non-empty text")
    if value != value.strip():
        raise ContractValidationError(
            f"{label} must not contain leading or trailing whitespace"
        )
    return value


def _exact_fields(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    label: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractValidationError(
            f"{label} fields must equal {sorted(expected)}; got {sorted(actual)}"
        )


def _text_sequence(value: Any, *, label: str) -> tuple[str, ...]:
    return tuple(
        _text(item, label=f"{label}[]") for item in _sequence(value, label=label)
    )


def _canonical_integer(value: Any, *, label: str) -> int:
    text = _text(value, label=label)
    if INTEGER_PATTERN.fullmatch(text) is None:
        raise ContractValidationError(
            f"{label} must be a non-negative canonical integer string"
        )
    return int(text)


def _fixed_scale_decimal(value: Any, *, label: str, scale: int) -> str:
    text = _text(value, label=label)
    pattern = re.compile(rf"^(?:0|[1-9][0-9]*)\.[0-9]{{{scale}}}$")
    if pattern.fullmatch(text) is None:
        raise ContractValidationError(
            f"{label} must be a non-negative decimal with exactly {scale} places"
        )
    return text


def _validate_control_map(
    controls: Mapping[str, Any],
    control_id: str,
    years: tuple[str, ...],
    *,
    scale: int | None = None,
) -> dict[str, str]:
    raw = _mapping(controls.get(control_id), label=f"controls.{control_id}")
    if set(raw) != set(years):
        raise ContractValidationError(
            f"controls.{control_id} years must equal {list(years)}"
        )
    normalized: dict[str, str] = {}
    for year in years:
        if scale is None:
            normalized[year] = str(
                _canonical_integer(
                    raw[year],
                    label=f"controls.{control_id}.{year}",
                )
            )
        else:
            normalized[year] = _fixed_scale_decimal(
                raw[year],
                label=f"controls.{control_id}.{year}",
                scale=scale,
            )
    return normalized


def _load_case(
    case_path: Path,
) -> tuple[
    dict[str, Any],
    Path,
    Path,
    dict[str, Any],
    dict[str, dict[str, str]],
]:
    case_path = Path(case_path).resolve()
    case = strict_json_load(case_path)
    _exact_fields(
        case,
        {
            "schema_version",
            "case_id",
            "purpose",
            "declared_input_claim_ids",
            "preparation_recipe",
            "facts_contract",
            "control_facts_contract",
            "controls",
            "source_extraction_review",
            "reviewed_boundary",
            "files",
            "sources",
            "limitations",
        },
        label="case",
    )
    if case["schema_version"] != CASE_SCHEMA:
        raise ContractValidationError(f"schema_version must be {CASE_SCHEMA}")
    _text(case["case_id"], label="case_id")
    _text(case["purpose"], label="purpose")
    declared_input_claim_ids = _text_sequence(
        case["declared_input_claim_ids"],
        label="declared_input_claim_ids",
    )
    if len(declared_input_claim_ids) != len(set(declared_input_claim_ids)):
        raise ContractValidationError("declared_input_claim_ids must be unique")
    allowed_input_claim_ids = set(ALLOWED_OUTPUT_METRIC_IDS) | set(FORBIDDEN_CLAIM_IDS)
    unsupported_input_claim_ids = sorted(
        set(declared_input_claim_ids) - allowed_input_claim_ids
    )
    if unsupported_input_claim_ids:
        raise ContractValidationError(
            "declared_input_claim_ids contain unsupported claims: "
            f"{unsupported_input_claim_ids}"
        )

    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    _exact_fields(
        recipe,
        {
            "recipe_id",
            "engine_version",
            "arithmetic",
            "customer_aliases",
            "fiscal_years",
            "metric_ids",
            "coverage_ratio_unit",
            "coverage_ratio_scale",
            "coverage_ratio_rounding",
            "source_locator",
        },
        label="preparation_recipe",
    )
    if recipe["recipe_id"] != RECIPE_ID:
        raise ContractValidationError(f"recipe_id must be {RECIPE_ID}")
    if recipe["engine_version"] != ENGINE_VERSION:
        raise ContractValidationError(f"engine_version must be {ENGINE_VERSION}")
    if recipe["arithmetic"] != "integer_exact_with_declared_ratio_scale":
        raise ContractValidationError("unexpected preparation arithmetic")
    if (
        _text_sequence(
            recipe["customer_aliases"], label="preparation_recipe.customer_aliases"
        )
        != CUSTOMER_ALIASES
    ):
        raise ContractValidationError("customer_aliases contract changed")
    if (
        _text_sequence(recipe["fiscal_years"], label="preparation_recipe.fiscal_years")
        != FISCAL_YEARS
    ):
        raise ContractValidationError("fiscal_years contract changed")
    if (
        _text_sequence(recipe["metric_ids"], label="preparation_recipe.metric_ids")
        != METRIC_IDS
    ):
        raise ContractValidationError("metric_ids contract changed")
    scale = recipe["coverage_ratio_scale"]
    if type(scale) is not int or scale != 6:
        raise ContractValidationError("coverage_ratio_scale must be 6")
    if recipe["coverage_ratio_unit"] != "percent":
        raise ContractValidationError("coverage_ratio_unit must be percent")
    if recipe["coverage_ratio_rounding"] != "half_up_exact_integer":
        raise ContractValidationError(
            "coverage_ratio_rounding must be half_up_exact_integer"
        )
    _text(recipe["source_locator"], label="preparation_recipe.source_locator")

    facts_contract = _mapping(case["facts_contract"], label="facts_contract")
    _exact_fields(
        facts_contract,
        {
            "required_columns",
            "natural_key",
            "exact_row_count",
            "exact_expected_set",
            "numeric_contract",
        },
        label="facts_contract",
    )
    if (
        _text_sequence(
            facts_contract["required_columns"], label="facts_contract.required_columns"
        )
        != FACT_COLUMNS
    ):
        raise ContractValidationError("facts_contract.required_columns changed")
    if _text_sequence(
        facts_contract["natural_key"], label="facts_contract.natural_key"
    ) != ("customer_alias", "fiscal_year", "metric_id"):
        raise ContractValidationError("facts_contract.natural_key changed")
    if facts_contract["exact_row_count"] != 18:
        raise ContractValidationError("facts_contract.exact_row_count must be 18")
    if facts_contract["exact_expected_set"] is not True:
        raise ContractValidationError("facts_contract must require an exact set")
    _text(facts_contract["numeric_contract"], label="facts_contract.numeric_contract")

    control_facts_contract = _mapping(
        case["control_facts_contract"], label="control_facts_contract"
    )
    _exact_fields(
        control_facts_contract,
        {
            "required_columns",
            "natural_key",
            "exact_row_count",
            "exact_expected_set",
            "numeric_contract",
            "source_locators",
        },
        label="control_facts_contract",
    )
    if (
        _text_sequence(
            control_facts_contract["required_columns"],
            label="control_facts_contract.required_columns",
        )
        != CONTROL_FACT_COLUMNS
    ):
        raise ContractValidationError("control_facts_contract.required_columns changed")
    if _text_sequence(
        control_facts_contract["natural_key"],
        label="control_facts_contract.natural_key",
    ) != ("fiscal_year", "metric_id"):
        raise ContractValidationError("control_facts_contract.natural_key changed")
    if control_facts_contract["exact_row_count"] != 5:
        raise ContractValidationError(
            "control_facts_contract.exact_row_count must be 5"
        )
    if control_facts_contract["exact_expected_set"] is not True:
        raise ContractValidationError(
            "control_facts_contract must require an exact set"
        )
    _text(
        control_facts_contract["numeric_contract"],
        label="control_facts_contract.numeric_contract",
    )
    control_source_locators = _mapping(
        control_facts_contract["source_locators"],
        label="control_facts_contract.source_locators",
    )
    _exact_fields(
        control_source_locators,
        {"total_revenue", "total_accounts_receivable"},
        label="control_facts_contract.source_locators",
    )
    for metric_id in ("total_revenue", "total_accounts_receivable"):
        _text(
            control_source_locators[metric_id],
            label=f"control_facts_contract.source_locators.{metric_id}",
        )

    boundary = _mapping(case["reviewed_boundary"], label="reviewed_boundary")
    _exact_fields(
        boundary,
        {
            "status",
            "reviewed_on",
            "judgement_owner",
            "source_authority",
            "semantic_authority",
            "publication_status",
            "report_ready",
            "statement",
            "allowed_output_metric_ids",
            "forbidden_claim_ids",
            "accounts_receivable_coverage_unavailable_years",
        },
        label="reviewed_boundary",
    )
    if boundary["status"] != "reviewed":
        raise ContractValidationError("reviewed_boundary.status must be reviewed")
    try:
        date.fromisoformat(
            _text(boundary["reviewed_on"], label="reviewed_boundary.reviewed_on")
        )
    except ValueError as exc:
        raise ContractValidationError(
            "reviewed_boundary.reviewed_on must be an ISO date"
        ) from exc
    if boundary["source_authority"] != "receipt_and_review_only":
        raise ContractValidationError(
            "source authority must remain receipt/review only"
        )
    if boundary["semantic_authority"] != "reviewed_boundary_only":
        raise ContractValidationError(
            "semantic authority must remain reviewed-boundary only"
        )
    if boundary["publication_status"] != "withheld":
        raise ContractValidationError("publication must remain withheld")
    if boundary["report_ready"] is not False:
        raise ContractValidationError("report_ready must remain false")
    _text(boundary["judgement_owner"], label="reviewed_boundary.judgement_owner")
    _text(boundary["statement"], label="reviewed_boundary.statement")
    if (
        _text_sequence(
            boundary["allowed_output_metric_ids"],
            label="reviewed_boundary.allowed_output_metric_ids",
        )
        != ALLOWED_OUTPUT_METRIC_IDS
    ):
        raise ContractValidationError("allowed output metrics changed")
    if (
        _text_sequence(
            boundary["forbidden_claim_ids"],
            label="reviewed_boundary.forbidden_claim_ids",
        )
        != FORBIDDEN_CLAIM_IDS
    ):
        raise ContractValidationError("forbidden claim boundary changed")
    if _text_sequence(
        boundary["accounts_receivable_coverage_unavailable_years"],
        label=("reviewed_boundary.accounts_receivable_coverage_unavailable_years"),
    ) != ("2023",):
        raise ContractValidationError("AR coverage availability boundary changed")

    controls = _mapping(case["controls"], label="controls")
    _exact_fields(
        controls,
        {
            "total_revenue",
            "total_accounts_receivable",
            "disclosed_top_three_revenue_share",
            "disclosed_accounts_receivable_subtotal",
            "accounts_receivable_coverage_percent",
            "reported_share_hhi_contribution",
        },
        label="controls",
    )
    normalized_controls = {
        "total_revenue": _validate_control_map(controls, "total_revenue", FISCAL_YEARS),
        "total_accounts_receivable": _validate_control_map(
            controls,
            "total_accounts_receivable",
            ("2025", "2024"),
        ),
        "disclosed_top_three_revenue_share": _validate_control_map(
            controls,
            "disclosed_top_three_revenue_share",
            FISCAL_YEARS,
        ),
        "disclosed_accounts_receivable_subtotal": _validate_control_map(
            controls,
            "disclosed_accounts_receivable_subtotal",
            ("2025", "2024"),
        ),
        "accounts_receivable_coverage_percent": _validate_control_map(
            controls,
            "accounts_receivable_coverage_percent",
            ("2025", "2024"),
            scale=scale,
        ),
        "reported_share_hhi_contribution": _validate_control_map(
            controls,
            "reported_share_hhi_contribution",
            FISCAL_YEARS,
        ),
    }

    source_review = _mapping(
        case["source_extraction_review"],
        label="source_extraction_review",
    )
    _exact_fields(
        source_review,
        {
            "status",
            "reviewed_on",
            "reviewer",
            "basis",
            "authority",
        },
        label="source_extraction_review",
    )
    if source_review["status"] != "reviewed":
        raise ContractValidationError(
            "source_extraction_review.status must be reviewed"
        )
    try:
        date.fromisoformat(
            _text(
                source_review["reviewed_on"],
                label="source_extraction_review.reviewed_on",
            )
        )
    except ValueError as exc:
        raise ContractValidationError(
            "source_extraction_review.reviewed_on must be an ISO date"
        ) from exc
    _text(source_review["reviewer"], label="source_extraction_review.reviewer")
    _text(source_review["basis"], label="source_extraction_review.basis")
    if source_review["authority"] != "receipt_and_review_only":
        raise ContractValidationError(
            "source_extraction_review.authority must remain receipt/review only"
        )

    files = _mapping(case["files"], label="files")
    _exact_fields(
        files,
        {"exact_extracted_facts", "exact_control_facts"},
        label="files",
    )
    fact_spec = _mapping(
        files["exact_extracted_facts"], label="files.exact_extracted_facts"
    )
    _exact_fields(
        fact_spec,
        {"path", "sha256"},
        label="files.exact_extracted_facts",
    )
    facts_path = resolve_local_file(
        case_path.parent,
        fact_spec["path"],
        label="files.exact_extracted_facts.path",
    )
    declared_digest = _text(
        fact_spec["sha256"], label="files.exact_extracted_facts.sha256"
    )
    if SHA256_PATTERN.fullmatch(declared_digest) is None:
        raise ContractValidationError("fact-file SHA-256 is malformed")
    if file_sha256(facts_path) != declared_digest:
        raise ContractValidationError("fact-file SHA-256 does not match")
    control_fact_spec = _mapping(
        files["exact_control_facts"], label="files.exact_control_facts"
    )
    _exact_fields(
        control_fact_spec,
        {"path", "sha256"},
        label="files.exact_control_facts",
    )
    control_facts_path = resolve_local_file(
        case_path.parent,
        control_fact_spec["path"],
        label="files.exact_control_facts.path",
    )
    declared_control_digest = _text(
        control_fact_spec["sha256"],
        label="files.exact_control_facts.sha256",
    )
    if SHA256_PATTERN.fullmatch(declared_control_digest) is None:
        raise ContractValidationError("control-fact-file SHA-256 is malformed")
    if file_sha256(control_facts_path) != declared_control_digest:
        raise ContractValidationError("control-fact-file SHA-256 does not match")

    raw_sources = _sequence(case["sources"], label="sources")
    if len(raw_sources) != 1:
        raise ContractValidationError("sources must contain exactly one filing")
    source = dict(_mapping(raw_sources[0], label="sources[0]"))
    _exact_fields(
        source,
        {
            "source_id",
            "publisher",
            "title",
            "form",
            "cik",
            "accession",
            "filed_date",
            "period_end",
            "url",
            "byte_count",
            "sha256",
            "role",
        },
        label="sources[0]",
    )
    for field in (
        "source_id",
        "publisher",
        "title",
        "form",
        "cik",
        "accession",
        "filed_date",
        "period_end",
        "url",
        "sha256",
        "role",
    ):
        _text(source[field], label=f"sources[0].{field}")
    if source["form"] != "10-K":
        raise ContractValidationError("source form must be 10-K")
    if not str(source["url"]).startswith("https://"):
        raise ContractValidationError("source URL must use https")
    for field in ("filed_date", "period_end"):
        try:
            date.fromisoformat(str(source[field]))
        except ValueError as exc:
            raise ContractValidationError(
                f"sources[0].{field} must be an ISO date"
            ) from exc
    if type(source["byte_count"]) is not int or source["byte_count"] <= 0:
        raise ContractValidationError("source byte_count must be positive")
    if SHA256_PATTERN.fullmatch(str(source["sha256"])) is None:
        raise ContractValidationError("source SHA-256 is malformed")
    limitations = _text_sequence(case["limitations"], label="limitations")
    if not limitations:
        raise ContractValidationError("limitations must not be empty")
    return case, facts_path, control_facts_path, source, normalized_controls


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
            "identifiers": sorted({str(item) for item in identifiers}),
        }
    )


def _read_and_validate_facts(
    facts_path: Path,
    *,
    recipe: Mapping[str, Any],
    source_id: str,
    errors: list[dict[str, Any]],
) -> tuple[
    list[dict[str, str]],
    dict[tuple[str, str, str], int],
    dict[tuple[str, str, str], str],
]:
    rows = read_exact_csv(
        facts_path,
        columns=FACT_COLUMNS,
        label="exact extracted facts",
    )
    if len(rows) != 18:
        _add_error(
            errors,
            gate="exact_fact_set",
            code="unexpected_fact_row_count",
            message=f"expected 18 fact rows and received {len(rows)}",
        )

    values: dict[tuple[str, str, str], int] = {}
    fact_ids_by_key: dict[tuple[str, str, str], str] = {}
    fact_ids: list[str] = []
    natural_keys: list[tuple[str, str, str]] = []
    forbidden_metrics = set(FORBIDDEN_CLAIM_IDS)
    source_locator = str(recipe["source_locator"])
    for position, row in enumerate(rows, start=2):
        label = f"exact extracted facts row {position}"
        for column in FACT_COLUMNS:
            _text(row[column], label=f"{label}.{column}")
        alias = row["customer_alias"]
        year = row["fiscal_year"]
        metric_id = row["metric_id"]
        fact_id = row["fact_id"]
        key = (alias, year, metric_id)
        fact_ids.append(fact_id)
        natural_keys.append(key)
        if alias not in CUSTOMER_ALIASES:
            _add_error(
                errors,
                gate="alias_period_metric_contract",
                code="unsupported_customer_alias",
                message=f"{fact_id} uses unsupported anonymous alias {alias}",
                identifiers=(fact_id, alias),
            )
        if year not in FISCAL_YEARS:
            _add_error(
                errors,
                gate="alias_period_metric_contract",
                code="unsupported_fiscal_year",
                message=f"{fact_id} uses unsupported fiscal year {year}",
                identifiers=(fact_id, year),
            )
        if metric_id not in METRIC_IDS:
            _add_error(
                errors,
                gate="alias_period_metric_contract",
                code="unsupported_metric_id",
                message=f"{fact_id} uses unsupported metric {metric_id}",
                identifiers=(fact_id, metric_id),
            )
            if metric_id in forbidden_metrics:
                _add_error(
                    errors,
                    gate="claim_abstention",
                    code="forbidden_claim_present",
                    message=f"{fact_id} attempts forbidden claim {metric_id}",
                    identifiers=(fact_id, metric_id),
                )
        expected_fact_id = f"udc_{year}_{alias.lower()}_{metric_id}"
        if fact_id != expected_fact_id:
            _add_error(
                errors,
                gate="exact_fact_set",
                code="fact_id_contract_mismatch",
                message=f"{fact_id} does not match its natural key",
                identifiers=(fact_id, expected_fact_id),
            )
        value = _canonical_integer(row["value"], label=f"{label}.value")
        expected_unit = {
            "revenue_share": "percent",
            "accounts_receivable": "USD_thousands",
        }.get(metric_id)
        if expected_unit is not None and row["unit"] != expected_unit:
            _add_error(
                errors,
                gate="unit_increment_contract",
                code="unit_mismatch",
                message=f"{fact_id} must use {expected_unit}",
                identifiers=(fact_id, row["unit"]),
            )
        if row["reported_increment"] != "1":
            _add_error(
                errors,
                gate="unit_increment_contract",
                code="reported_increment_mismatch",
                message=f"{fact_id} must use reported increment 1",
                identifiers=(fact_id, row["reported_increment"]),
            )
        if metric_id == "revenue_share" and value > 100:
            _add_error(
                errors,
                gate="unit_increment_contract",
                code="revenue_share_out_of_range",
                message=f"{fact_id} revenue share exceeds 100 percent",
                identifiers=(fact_id,),
            )
        if row["source_id"] != source_id:
            _add_error(
                errors,
                gate="source_contract",
                code="unknown_source",
                message=f"{fact_id} does not use the reviewed filing source",
                identifiers=(fact_id, row["source_id"]),
            )
        if row["source_locator"] != source_locator:
            _add_error(
                errors,
                gate="source_contract",
                code="source_locator_mismatch",
                message=f"{fact_id} does not use the reviewed source locator",
                identifiers=(fact_id,),
            )
        if key not in values:
            values[key] = value
            fact_ids_by_key[key] = fact_id

    duplicate_fact_ids = sorted(
        fact_id for fact_id, count in Counter(fact_ids).items() if count > 1
    )
    for fact_id in duplicate_fact_ids:
        _add_error(
            errors,
            gate="duplicate_control",
            code="duplicate_fact_id",
            message=f"duplicate fact_id {fact_id}",
            identifiers=(fact_id,),
        )
    duplicate_keys = sorted(
        key for key, count in Counter(natural_keys).items() if count > 1
    )
    for alias, year, metric_id in duplicate_keys:
        _add_error(
            errors,
            gate="duplicate_control",
            code="duplicate_fact_natural_key",
            message=f"duplicate fact natural key {alias} {year} {metric_id}",
            identifiers=(alias, year, metric_id),
        )

    expected_keys = {
        (alias, year, metric_id)
        for year in FISCAL_YEARS
        for alias in CUSTOMER_ALIASES
        for metric_id in METRIC_IDS
    }
    actual_keys = set(natural_keys)
    for alias, year, metric_id in sorted(expected_keys - actual_keys):
        _add_error(
            errors,
            gate="exact_fact_set",
            code="missing_fact",
            message=f"missing fact for {alias} {year} {metric_id}",
            identifiers=(alias, year, metric_id),
        )
    for alias, year, metric_id in sorted(actual_keys - expected_keys):
        _add_error(
            errors,
            gate="exact_fact_set",
            code="unexpected_fact",
            message=f"unexpected fact for {alias} {year} {metric_id}",
            identifiers=(alias, year, metric_id),
        )
    return rows, values, fact_ids_by_key


def _read_and_validate_control_facts(
    control_facts_path: Path,
    *,
    control_contract: Mapping[str, Any],
    source_id: str,
    golden_controls: Mapping[str, Mapping[str, str]],
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    rows = read_exact_csv(
        control_facts_path,
        columns=CONTROL_FACT_COLUMNS,
        label="exact control facts",
    )
    if len(rows) != 5:
        _add_error(
            errors,
            gate="exact_fact_set",
            code="unexpected_control_fact_row_count",
            message=f"expected 5 control fact rows and received {len(rows)}",
        )
    source_locators = _mapping(
        control_contract["source_locators"],
        label="control_facts_contract.source_locators",
    )
    control_ids: list[str] = []
    natural_keys: list[tuple[str, str]] = []
    values: dict[str, dict[str, str]] = {
        "total_revenue": {},
        "total_accounts_receivable": {},
    }
    expected_keys = {
        *(("total_revenue", year) for year in FISCAL_YEARS),
        *(("total_accounts_receivable", year) for year in ("2025", "2024")),
    }
    for position, row in enumerate(rows, start=2):
        label = f"exact control facts row {position}"
        for column in CONTROL_FACT_COLUMNS:
            _text(row[column], label=f"{label}.{column}")
        control_id = row["control_id"]
        year = row["fiscal_year"]
        metric_id = row["metric_id"]
        key = (metric_id, year)
        control_ids.append(control_id)
        natural_keys.append(key)
        if key not in expected_keys:
            _add_error(
                errors,
                gate="exact_fact_set",
                code="unexpected_control_fact",
                message=f"unexpected control fact for {metric_id} {year}",
                identifiers=(control_id, metric_id, year),
            )
        expected_control_id = f"udc_{year}_{metric_id}"
        if control_id != expected_control_id:
            _add_error(
                errors,
                gate="exact_fact_set",
                code="control_id_contract_mismatch",
                message=f"{control_id} does not match its natural key",
                identifiers=(control_id, expected_control_id),
            )
        value = str(_canonical_integer(row["value"], label=f"{label}.value"))
        if row["unit"] != "USD_thousands":
            _add_error(
                errors,
                gate="unit_increment_contract",
                code="control_unit_mismatch",
                message=f"{control_id} must use USD_thousands",
                identifiers=(control_id, row["unit"]),
            )
        if row["reported_increment"] != "1":
            _add_error(
                errors,
                gate="unit_increment_contract",
                code="control_increment_mismatch",
                message=f"{control_id} must use reported increment 1",
                identifiers=(control_id, row["reported_increment"]),
            )
        if row["source_id"] != source_id:
            _add_error(
                errors,
                gate="source_contract",
                code="unknown_control_source",
                message=f"{control_id} does not use the reviewed filing source",
                identifiers=(control_id, row["source_id"]),
            )
        if (
            metric_id in source_locators
            and row["source_locator"] != source_locators[metric_id]
        ):
            _add_error(
                errors,
                gate="source_contract",
                code="control_source_locator_mismatch",
                message=f"{control_id} does not use the reviewed source locator",
                identifiers=(control_id,),
            )
        if metric_id in values and year not in values[metric_id]:
            values[metric_id][year] = value
        expected_value = golden_controls.get(metric_id, {}).get(year)
        if expected_value is not None and value != expected_value:
            _add_error(
                errors,
                gate="control_values",
                code="source_control_value_mismatch",
                message=(
                    f"{control_id} extracted value {value} does not match "
                    f"golden control {expected_value}"
                ),
                identifiers=(control_id,),
            )

    for control_id, count in sorted(Counter(control_ids).items()):
        if count > 1:
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_control_id",
                message=f"duplicate control_id {control_id}",
                identifiers=(control_id,),
            )
    for key, count in sorted(Counter(natural_keys).items()):
        if count > 1:
            metric_id, year = key
            _add_error(
                errors,
                gate="duplicate_control",
                code="duplicate_control_natural_key",
                message=f"duplicate control natural key {metric_id} {year}",
                identifiers=(metric_id, year),
            )
    actual_keys = set(natural_keys)
    for metric_id, year in sorted(expected_keys - actual_keys):
        _add_error(
            errors,
            gate="exact_fact_set",
            code="missing_control_fact",
            message=f"missing control fact for {metric_id} {year}",
            identifiers=(metric_id, year),
        )
    return rows, values


def _rounded_percent(
    numerator: int,
    denominator: int,
    *,
    scale: int,
) -> str:
    if numerator < 0 or denominator <= 0:
        raise ContractValidationError("coverage ratio inputs are invalid")
    factor = 10**scale
    quotient, remainder = divmod(numerator * 100 * factor, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    whole, fractional = divmod(quotient, factor)
    return f"{whole}.{fractional:0{scale}d}"


def _summary_row(
    year: str,
    metric_id: str,
    value: str,
    *,
    unit: str,
    reported_increment: str,
    declared_scale: int,
    characterization: str,
    availability_status: str = "available",
) -> dict[str, str]:
    return {
        "summary_id": f"udc_{year}_{metric_id}",
        "fiscal_year": year,
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "reported_increment": reported_increment,
        "declared_scale": str(declared_scale),
        "availability_status": availability_status,
        "characterization": characterization,
    }


def _check_expected(
    *,
    actual: str,
    expected: str,
    year: str,
    control_id: str,
    gate: str,
    errors: list[dict[str, Any]],
) -> None:
    if actual != expected:
        _add_error(
            errors,
            gate=gate,
            code="derived_control_mismatch",
            message=(
                f"{control_id} for {year} calculated as {actual}; expected {expected}"
            ),
            identifiers=(control_id, year),
        )


def _derive_summary(
    values: Mapping[tuple[str, str, str], int],
    fact_ids_by_key: Mapping[tuple[str, str, str], str],
    *,
    source_controls: Mapping[str, Mapping[str, str]],
    golden_controls: Mapping[str, Mapping[str, str]],
    scale: int,
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows: list[dict[str, str]] = []
    lineage: list[dict[str, Any]] = []

    def append(
        row: dict[str, str],
        *,
        fact_ids: Sequence[str] = (),
        control_refs: Sequence[str] = (),
    ) -> None:
        rows.append(row)
        lineage.append(
            {
                "summary_id": row["summary_id"],
                "input_fact_ids": sorted(fact_ids),
                "control_refs": sorted(control_refs),
            }
        )

    for year in FISCAL_YEARS:
        if year not in source_controls["total_revenue"]:
            continue
        append(
            _summary_row(
                year,
                "total_revenue_control",
                source_controls["total_revenue"][year],
                unit="USD_thousands",
                reported_increment="1",
                declared_scale=0,
                characterization="issuer_reported_total_control",
            ),
            control_refs=(f"udc_{year}_total_revenue",),
        )
    for year in ("2025", "2024"):
        if year not in source_controls["total_accounts_receivable"]:
            continue
        append(
            _summary_row(
                year,
                "total_accounts_receivable_control",
                source_controls["total_accounts_receivable"][year],
                unit="USD_thousands",
                reported_increment="1",
                declared_scale=0,
                characterization="issuer_reported_total_control",
            ),
            control_refs=(f"udc_{year}_total_accounts_receivable",),
        )

    for year in FISCAL_YEARS:
        keys = [(alias, year, "revenue_share") for alias in CUSTOMER_ALIASES]
        if not all(key in values and key in fact_ids_by_key for key in keys):
            continue
        shares = [values[key] for key in keys]
        fact_ids = [fact_ids_by_key[key] for key in keys]
        top_three = str(sum(shares))
        _check_expected(
            actual=top_three,
            expected=golden_controls["disclosed_top_three_revenue_share"][year],
            year=year,
            control_id="disclosed_top_three_revenue_share",
            gate="revenue_share_subtotals",
            errors=errors,
        )
        if sum(shares) > 100:
            _add_error(
                errors,
                gate="revenue_share_subtotals",
                code="reported_share_subtotal_exceeds_100",
                message=f"reported customer shares for {year} exceed 100 percent",
                identifiers=(year,),
            )
        append(
            _summary_row(
                year,
                "disclosed_top_three_revenue_share",
                top_three,
                unit="percent",
                reported_increment="1",
                declared_scale=0,
                characterization="sum_of_reported_whole_percentage_shares",
            ),
            fact_ids=fact_ids,
        )

        hhi_contribution = str(sum(share * share for share in shares))
        _check_expected(
            actual=hhi_contribution,
            expected=golden_controls["reported_share_hhi_contribution"][year],
            year=year,
            control_id="reported_share_hhi_contribution",
            gate="reported_share_hhi_contribution",
            errors=errors,
        )
        append(
            _summary_row(
                year,
                "reported_share_hhi_contribution",
                hhi_contribution,
                unit="hhi_points",
                reported_increment="1",
                declared_scale=0,
                characterization="incomplete_reported_share_contribution_only",
            ),
            fact_ids=fact_ids,
        )

    for year in ("2025", "2024"):
        keys = [(alias, year, "accounts_receivable") for alias in CUSTOMER_ALIASES]
        if (
            not all(key in values and key in fact_ids_by_key for key in keys)
            or year not in source_controls["total_accounts_receivable"]
        ):
            continue
        fact_ids = [fact_ids_by_key[key] for key in keys]
        subtotal_int = sum(values[key] for key in keys)
        subtotal = str(subtotal_int)
        total_ar = int(source_controls["total_accounts_receivable"][year])
        _check_expected(
            actual=subtotal,
            expected=golden_controls["disclosed_accounts_receivable_subtotal"][year],
            year=year,
            control_id="disclosed_accounts_receivable_subtotal",
            gate="accounts_receivable_subtotals",
            errors=errors,
        )
        if subtotal_int > total_ar:
            _add_error(
                errors,
                gate="accounts_receivable_subtotals",
                code="customer_ar_subtotal_exceeds_total_ar",
                message=f"disclosed customer AR subtotal exceeds total AR for {year}",
                identifiers=(year,),
            )
        append(
            _summary_row(
                year,
                "disclosed_accounts_receivable_subtotal",
                subtotal,
                unit="USD_thousands",
                reported_increment="1",
                declared_scale=0,
                characterization=(
                    "sum_of_disclosed_customer_ar_for_year_with_total_ar_control"
                ),
            ),
            fact_ids=fact_ids,
        )

        if total_ar <= 0:
            _add_error(
                errors,
                gate="accounts_receivable_coverage",
                code="invalid_total_accounts_receivable_denominator",
                message=(
                    f"total accounts receivable must be positive to calculate "
                    f"coverage for {year}"
                ),
                identifiers=(year,),
            )
            continue
        coverage = _rounded_percent(subtotal_int, total_ar, scale=scale)
        _check_expected(
            actual=coverage,
            expected=golden_controls["accounts_receivable_coverage_percent"][year],
            year=year,
            control_id="accounts_receivable_coverage_percent",
            gate="accounts_receivable_coverage",
            errors=errors,
        )
        append(
            _summary_row(
                year,
                "accounts_receivable_coverage_percent",
                coverage,
                unit="percent",
                reported_increment=f"0.{('0' * (scale - 1))}1",
                declared_scale=scale,
                characterization=(
                    "derived_reported_customer_ar_coverage_at_declared_scale"
                ),
            ),
            fact_ids=fact_ids,
            control_refs=(f"udc_{year}_total_accounts_receivable",),
        )

    unavailable_year = "2023"
    unavailable_keys = [
        (alias, unavailable_year, "accounts_receivable") for alias in CUSTOMER_ALIASES
    ]
    append(
        _summary_row(
            unavailable_year,
            "accounts_receivable_coverage_percent",
            "",
            unit="percent",
            reported_increment=f"0.{('0' * (scale - 1))}1",
            declared_scale=scale,
            availability_status="unavailable",
            characterization=(
                "unavailable_without_frozen_total_accounts_receivable_control"
            ),
        ),
        fact_ids=[
            fact_ids_by_key[key] for key in unavailable_keys if key in fact_ids_by_key
        ],
    )

    output_metric_ids = {row["metric_id"] for row in rows}
    forbidden_emitted = sorted(output_metric_ids & set(FORBIDDEN_CLAIM_IDS))
    unexpected_output_metrics = sorted(
        output_metric_ids - set(ALLOWED_OUTPUT_METRIC_IDS)
    )
    for metric_id in forbidden_emitted:
        _add_error(
            errors,
            gate="claim_abstention",
            code="forbidden_output_claim",
            message=f"forbidden output claim emitted: {metric_id}",
            identifiers=(metric_id,),
        )
    for metric_id in unexpected_output_metrics:
        _add_error(
            errors,
            gate="claim_abstention",
            code="unexpected_output_metric",
            message=f"unexpected output metric emitted: {metric_id}",
            identifiers=(metric_id,),
        )
    rows.sort(
        key=lambda row: (
            ALLOWED_OUTPUT_METRIC_IDS.index(row["metric_id"]),
            FISCAL_YEARS.index(row["fiscal_year"]),
        )
    )
    lineage.sort(key=lambda item: str(item["summary_id"]))
    return rows, lineage


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


def _write_csv(
    path: Path,
    columns: tuple[str, ...],
    rows: Sequence[Mapping[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(columns),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _artifact_record(
    artifact_id: str,
    path: Path,
    media_type: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path.name,
        "media_type": media_type,
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def prepare_customer_concentration_case(
    case_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Prepare one frozen filing-disclosure case and return reconciliation."""

    case_path = Path(case_path).resolve()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in PRODUCER_OUTPUT_NAMES:
        (output_dir / name).unlink(missing_ok=True)
    unexpected_entries = sorted(path.name for path in output_dir.iterdir())
    if unexpected_entries:
        raise ContractValidationError(
            "output directory must be dedicated to this producer; "
            f"unregistered entries: {', '.join(unexpected_entries)}"
        )
    output_paths = {
        "customer_concentration_summary": (
            output_dir / "customer_concentration_summary.csv"
        ),
        "exceptions": output_dir / "exceptions.csv",
        "reconciliation": output_dir / "reconciliation.json",
        "prepared_evidence_manifest": output_dir / "prepared_evidence_manifest.json",
    }

    case, facts_path, control_facts_path, source, controls = _load_case(case_path)
    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    errors: list[dict[str, Any]] = []
    fact_rows, values, fact_ids_by_key = _read_and_validate_facts(
        facts_path,
        recipe=recipe,
        source_id=str(source["source_id"]),
        errors=errors,
    )
    control_fact_rows, source_controls = _read_and_validate_control_facts(
        control_facts_path,
        control_contract=_mapping(
            case["control_facts_contract"],
            label="control_facts_contract",
        ),
        source_id=str(source["source_id"]),
        golden_controls=controls,
        errors=errors,
    )
    summary_rows, summary_lineage = _derive_summary(
        values,
        fact_ids_by_key,
        source_controls=source_controls,
        golden_controls=controls,
        scale=int(recipe["coverage_ratio_scale"]),
        errors=errors,
    )
    declared_input_claims = set(
        _text_sequence(
            case["declared_input_claim_ids"],
            label="declared_input_claim_ids",
        )
    )
    declared_forbidden_claims = sorted(declared_input_claims & set(FORBIDDEN_CLAIM_IDS))
    for claim_id in declared_forbidden_claims:
        _add_error(
            errors,
            gate="claim_abstention",
            code="forbidden_declared_input_claim",
            message=f"declared input requests forbidden claim {claim_id}",
            identifiers=(claim_id,),
        )
    errors.sort(
        key=lambda item: (
            str(item["gate"]),
            str(item["code"]),
            str(item["message"]),
            tuple(item["identifiers"]),
        )
    )
    status = "passed" if not errors else "failed"
    forbidden_input_claims = sorted(
        ({row["metric_id"] for row in fact_rows} | declared_input_claims)
        & set(FORBIDDEN_CLAIM_IDS)
    )
    claim_abstention_failed = any(
        error["gate"] == "claim_abstention" for error in errors
    )
    reconciliation: dict[str, Any] = {
        "schema_version": RECONCILIATION_SCHEMA,
        "case_id": str(case["case_id"]),
        "recipe": {
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "arithmetic": str(recipe["arithmetic"]),
            "coverage_ratio_scale": int(recipe["coverage_ratio_scale"]),
            "coverage_ratio_rounding": str(recipe["coverage_ratio_rounding"]),
        },
        "status": status,
        "publication_status": "withheld",
        "report_ready": False,
        "counts": {
            "fact_rows": len(fact_rows),
            "control_fact_rows": len(control_fact_rows),
            "unique_fact_ids": len({row["fact_id"] for row in fact_rows}),
            "unique_natural_keys": len(
                {
                    (
                        row["customer_alias"],
                        row["fiscal_year"],
                        row["metric_id"],
                    )
                    for row in fact_rows
                }
            ),
            "unique_control_ids": len({row["control_id"] for row in control_fact_rows}),
            "unique_control_natural_keys": len(
                {(row["fiscal_year"], row["metric_id"]) for row in control_fact_rows}
            ),
            "summary_results": len(summary_rows),
            "exception_rows": len(errors),
            "errors": len(errors),
        },
        "checks": _checks(errors),
        "summary_results": summary_rows,
        "availability_results": [
            {
                "summary_id": "udc_2023_accounts_receivable_coverage_percent",
                "fiscal_year": "2023",
                "metric_id": "accounts_receivable_coverage_percent",
                "status": "unavailable",
                "reason": (
                    "The frozen source-control set contains no 2023 total "
                    "accounts-receivable denominator."
                ),
            }
        ],
        "claim_abstention": {
            "status": "failed" if claim_abstention_failed else "passed",
            "forbidden_claim_ids": list(FORBIDDEN_CLAIM_IDS),
            "offending_input_claim_ids": forbidden_input_claims,
            "emitted_forbidden_claim_ids": sorted(
                {row["metric_id"] for row in summary_rows} & set(FORBIDDEN_CLAIM_IDS)
            ),
        },
        "authority_boundary": {
            "source": "receipt_and_review_only",
            "semantic": "reviewed_boundary_only",
        },
        "errors": errors,
        "warnings": [
            {
                "code": "reported_share_hhi_is_incomplete",
                "message": (
                    "Squared whole-percentage shares are a reported-share "
                    "contribution only, not full HHI or an HHI lower bound."
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
    exception_rows = [
        {
            "error_id": f"error_{position:03d}",
            "gate": str(error["gate"]),
            "code": str(error["code"]),
            "message": str(error["message"]),
            "identifiers": json.dumps(
                error["identifiers"],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        for position, error in enumerate(errors, start=1)
    ]
    _write_csv(output_paths["exceptions"], EXCEPTION_COLUMNS, exception_rows)
    write_json(output_paths["reconciliation"], reconciliation)
    if errors:
        return reconciliation

    _write_csv(
        output_paths["customer_concentration_summary"],
        SUMMARY_COLUMNS,
        summary_rows,
    )
    output_artifacts = sorted(
        [
            _artifact_record(
                "customer_concentration_summary",
                output_paths["customer_concentration_summary"],
                "text/csv",
            ),
            _artifact_record(
                "exceptions",
                output_paths["exceptions"],
                "text/csv",
            ),
            _artifact_record(
                "reconciliation",
                output_paths["reconciliation"],
                "application/json",
            ),
        ],
        key=lambda item: str(item["artifact_id"]),
    )
    boundary = _mapping(case["reviewed_boundary"], label="reviewed_boundary")
    engine_path = Path(__file__).resolve()
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "case_id": str(case["case_id"]),
        "preparation_status": "passed",
        "publication_status": "withheld",
        "report_ready": False,
        "case_contract": {
            "path": case_path.name,
            "sha256": file_sha256(case_path),
        },
        "inputs": sorted(
            [
                {
                    "artifact_id": "exact_control_facts",
                    "path": control_facts_path.name,
                    "sha256": file_sha256(control_facts_path),
                    "size_bytes": control_facts_path.stat().st_size,
                },
                {
                    "artifact_id": "exact_extracted_facts",
                    "path": facts_path.name,
                    "sha256": file_sha256(facts_path),
                    "size_bytes": facts_path.stat().st_size,
                },
            ],
            key=lambda item: str(item["artifact_id"]),
        ),
        "recipe": {
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "engine_path": "scripts/prepare_customer_concentration_case.py",
            "engine_sha256": file_sha256(engine_path),
            "arithmetic": str(recipe["arithmetic"]),
            "coverage_ratio_scale": int(recipe["coverage_ratio_scale"]),
            "coverage_ratio_rounding": str(recipe["coverage_ratio_rounding"]),
        },
        "source_receipts": [source],
        "source_extraction_review": dict(
            _mapping(
                case["source_extraction_review"],
                label="source_extraction_review",
            )
        ),
        "reviewed_boundary": dict(boundary),
        "lineage": {
            "grain": "summary_metric_and_fiscal_year",
            "summary_metric_sources": summary_lineage,
        },
        "reconciliation": {
            "status": "passed",
            "sha256": file_sha256(output_paths["reconciliation"]),
        },
        "outputs": output_artifacts,
        "canonical_output_set_sha256": canonical_json_sha256(output_artifacts),
        "downstream_readiness": {
            "status": "not_assessed",
            "report_ready": False,
            "semantic_compatibility": "not_assessed",
            "render_compatibility": "not_assessed",
            "evidence_sealing": "not_assessed",
        },
    }
    write_json(output_paths["prepared_evidence_manifest"], manifest)
    return reconciliation


def main(argv: Sequence[str] | None = None) -> int:
    """Run the customer-concentration preparation command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="Path to case.json")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for deterministic preparation outputs",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = prepare_customer_concentration_case(args.case, args.output_dir)
    except (ContractValidationError, KeyError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "Customer-concentration preparation %s with %s error(s)",
        result["status"],
        result["counts"]["errors"],
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
