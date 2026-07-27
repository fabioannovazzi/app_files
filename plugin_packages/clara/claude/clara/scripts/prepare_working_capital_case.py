#!/usr/bin/env python3
"""Prepare an exact public working-capital schedule from reviewed mechanics.

The deterministic rules in this module are justified by mechanically
verifiable correctness and auditability: strict schemas, pinned local inputs,
exact Decimal arithmetic, statement footing, cumulative-flow de-cumulation,
and exact replay. The module does not select the working-capital definition,
equate unlike source captions, allocate stock-flow residuals, normalize
balances, or judge whether the reviewed policy is economically appropriate.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    ExactDecimalPolicy,
    canonical_json_sha256,
    decimal_text,
    exact_decimal_context,
    file_sha256,
    is_on_increment,
    parse_decimal,
    read_exact_csv,
    resolve_local_file,
    strict_json_load,
    write_json,
)

__all__ = [
    "CALCULATION_PRECISION",
    "MAX_INPUT_DECIMAL_DIGITS",
    "MAX_INPUT_DECIMAL_SCALE",
    "main",
    "prepare_working_capital_case",
]

LOGGER = logging.getLogger(__name__)

CASE_SCHEMA = "clara.working_capital_preparation_case.v1"
POLICY_SCHEMA = "clara.reviewed_working_capital_policy.v1"
RECONCILIATION_SCHEMA = "clara.working_capital_reconciliation.v1"
MANIFEST_SCHEMA = "clara.working_capital_evidence_manifest.v1"
RECIPE_ID = "public_working_capital_from_reviewed_policy.v1"
ENGINE_VERSION = "1.0.0"
DE_CUMULATION_METHOD = "current_cumulative_minus_prior_cumulative_first_prior_zero"

MAX_INPUT_DECIMAL_DIGITS = 38
MAX_INPUT_DECIMAL_SCALE = 6
CALCULATION_PRECISION = 128
DECIMAL_POLICY = ExactDecimalPolicy(
    max_digits=MAX_INPUT_DECIMAL_DIGITS,
    max_scale=MAX_INPUT_DECIMAL_SCALE,
    calculation_precision=CALCULATION_PRECISION,
)

PUBLIC_FACT_COLUMNS = (
    "fact_id",
    "fact_kind",
    "period_label",
    "period_start",
    "period_end",
    "period_grain",
    "fact_key",
    "source_caption",
    "source_value",
    "unit",
    "source_sign_convention",
    "source_id",
    "source_locator",
)
SCHEDULE_COLUMNS = (
    "period_label",
    "period_end",
    "ar_net",
    "inventory",
    "other_current_assets",
    "accounts_payable",
    "accrued_liabilities",
    "accrued_payroll",
    "operating_nwc",
    "prior_period_end",
    "delta_operating_nwc",
    "expected_cash_impact",
    "unit",
    "policy_id",
)
BRIDGE_COLUMNS = (
    "bridge_row_id",
    "row_kind",
    "period_start",
    "period_end",
    "cumulative_cash_flow_change",
    "prior_cumulative_cash_flow_change",
    "period_cash_flow_change",
    "delta_operating_nwc",
    "expected_cash_impact",
    "stock_flow_residual",
    "residual_status",
    "unit",
    "policy_id",
)
DISCRETE_CASH_FLOW_COLUMNS = (
    "quarter",
    "period_start",
    "period_end",
    "trade_and_other_accounts_receivable_change",
    "inventory_change",
    "other_assets_change",
    "accounts_payable_and_accrued_liabilities_change",
    "accrued_payroll_and_related_expenses_change",
    "cumulative_cash_flow_change",
    "prior_cumulative_cash_flow_change",
    "discrete_cash_flow_change",
    "unit",
    "source_sign_convention",
    "current_cumulative_source_id",
    "prior_cumulative_source_id",
    "policy_id",
)
EXCEPTION_COLUMNS = (
    "error_id",
    "gate",
    "code",
    "message",
    "identifiers",
)

BALANCE_SHEET_FACT_KEYS = (
    "accounts_payable",
    "accrued_liabilities",
    "accrued_payroll_and_related_expenses",
    "cash_and_cash_equivalents",
    "income_taxes_payable",
    "inventories",
    "other_current_assets",
    "short_term_borrowings",
    "total_current_assets",
    "total_current_liabilities",
    "trade_and_other_accounts_receivable_net",
)
CASH_FLOW_FACT_KEYS = (
    "accounts_payable_and_accrued_liabilities",
    "accrued_payroll_and_related_expenses",
    "inventories",
    "other_assets",
    "trade_and_other_accounts_receivable",
)
SOURCE_CAPTIONS = {
    "accounts_payable": "Accounts payable",
    "accounts_payable_and_accrued_liabilities": (
        "Accounts payable and accrued liabilities"
    ),
    "accrued_liabilities": "Accrued liabilities",
    "accrued_payroll_and_related_expenses": ("Accrued payroll and related expenses"),
    "cash_and_cash_equivalents": "Cash and cash equivalents",
    "income_taxes_payable": "Income taxes payable",
    "inventories": "Inventories",
    "other_assets": "Other assets",
    "other_current_assets": "Other current assets",
    "short_term_borrowings": "Short-term borrowings",
    "total_current_assets": "Total current assets",
    "total_current_liabilities": "Total current liabilities",
    "trade_and_other_accounts_receivable": ("Trade and other accounts receivable"),
    "trade_and_other_accounts_receivable_net": (
        "Trade and other accounts receivable, net"
    ),
}
EXPECTED_BALANCE_FORMULA = (
    ("trade_and_other_accounts_receivable_net", "1"),
    ("inventories", "1"),
    ("other_current_assets", "1"),
    ("accounts_payable", "-1"),
    ("accrued_liabilities", "-1"),
    ("accrued_payroll_and_related_expenses", "-1"),
)
EXPECTED_CASH_FLOW_FORMULA = (
    ("trade_and_other_accounts_receivable", "1"),
    ("inventories", "1"),
    ("other_assets", "1"),
    ("accounts_payable_and_accrued_liabilities", "1"),
    ("accrued_payroll_and_related_expenses", "1"),
)
EXPECTED_EXCLUDED_KEYS = (
    "cash_and_cash_equivalents",
    "income_taxes_payable",
    "short_term_borrowings",
)
EXPECTED_PROHIBITED_ANALYTICS = (
    "days_inventory_outstanding",
    "days_payables_outstanding",
    "days_sales_outstanding",
    "normalization",
    "targets",
)
CHECK_IDS = (
    "balance_sheet_footing",
    "caption_boundary_contract",
    "cash_flow_de_cumulation",
    "duplicate_control",
    "fixture_control_tie_out",
    "input_contract",
    "operating_nwc_schedule",
    "period_contract",
    "policy_review_contract",
    "raw_fact_preservation",
    "source_contract",
    "stock_flow_bridge",
    "stock_roll_forward",
    "unit_contract",
)
PRODUCER_OUTPUT_NAMES = (
    "discrete_cash_flow_schedule.csv",
    "exceptions.csv",
    "prepared_evidence_manifest.json",
    "raw_fact_preservation.csv",
    "reconciliation.json",
    "stock_flow_bridge.csv",
    "working_capital_schedule.csv",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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
    result = value.strip()
    if not result and not allow_empty:
        raise ContractValidationError(f"{label} must be non-empty text")
    return result


def _identifier(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if IDENTIFIER_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a canonical identifier")
    return result


def _iso_date(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    try:
        date.fromisoformat(result)
    except ValueError as exc:
        raise ContractValidationError(f"{label} must be an ISO date") from exc
    return result


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    label: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(
            f"{label} contains unexpected fields: {unexpected}"
        )


def _error(
    gate: str,
    code: str,
    message: str,
    identifiers: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "gate": gate,
        "code": code,
        "message": message,
        "identifiers": sorted(set(identifiers)),
    }


def _validate_file_receipt(
    case_root: Path,
    value: Any,
    *,
    label: str,
) -> Path:
    receipt = _mapping(value, label=label)
    _exact_fields(
        receipt,
        required=frozenset({"path", "sha256"}),
        label=label,
    )
    declared_sha = _text(receipt["sha256"], label=f"{label}.sha256")
    if SHA256_PATTERN.fullmatch(declared_sha) is None:
        raise ContractValidationError(f"{label}.sha256 must be a lowercase SHA-256")
    path = resolve_local_file(case_root, receipt["path"], label=f"{label}.path")
    if file_sha256(path) != declared_sha:
        raise ContractValidationError(f"{label} digest mismatch")
    return path


def _validate_sources(value: Any) -> list[Mapping[str, Any]]:
    sources = [
        _mapping(item, label=f"sources[{position}]")
        for position, item in enumerate(_sequence(value, label="sources"))
    ]
    if not sources:
        raise ContractValidationError("sources must not be empty")
    source_ids: list[str] = []
    for position, source in enumerate(sources):
        label = f"sources[{position}]"
        _exact_fields(
            source,
            required=frozenset(
                {
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
            ),
            label=label,
        )
        source_ids.append(_identifier(source["source_id"], label=f"{label}.source_id"))
        _text(source["title"], label=f"{label}.title")
        _text(source["form"], label=f"{label}.form")
        _text(source["accession"], label=f"{label}.accession")
        _iso_date(source["filed_date"], label=f"{label}.filed_date")
        if not _text(source["url"], label=f"{label}.url").startswith("https://"):
            raise ContractValidationError(f"{label}.url must use https")
        if type(source["byte_count"]) is not int or source["byte_count"] <= 0:
            raise ContractValidationError(f"{label}.byte_count must be positive")
        source_sha = _text(source["sha256"], label=f"{label}.sha256")
        if SHA256_PATTERN.fullmatch(source_sha) is None:
            raise ContractValidationError(f"{label}.sha256 must be a lowercase SHA-256")
        if source["role"] not in {"annual_control", "quarterly_control"}:
            raise ContractValidationError(f"{label}.role is invalid")
    duplicates = sorted(
        source_id for source_id, count in Counter(source_ids).items() if count > 1
    )
    if duplicates:
        raise ContractValidationError(f"sources contain duplicate IDs: {duplicates}")
    return sources


def _validate_case_shape(case: Mapping[str, Any]) -> dict[str, Any]:
    _exact_fields(
        case,
        required=frozenset(
            {
                "schema_version",
                "case_id",
                "purpose",
                "preparation_recipe",
                "fixture_controls",
                "files",
                "sources",
                "disclosure_boundary",
            }
        ),
        label="case",
    )
    if case["schema_version"] != CASE_SCHEMA:
        raise ContractValidationError(f"case.schema_version must be {CASE_SCHEMA}")
    _identifier(case["case_id"], label="case.case_id")
    _text(case["purpose"], label="case.purpose")

    recipe = _mapping(case["preparation_recipe"], label="preparation_recipe")
    _exact_fields(
        recipe,
        required=frozenset(
            {
                "recipe_id",
                "engine_version",
                "arithmetic",
                "currency",
                "unit",
                "reported_increment",
                "policy_id",
                "policy_version",
                "balance_sheet_periods",
                "cash_flow_cumulative_periods",
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
    if recipe["currency"] != "USD" or recipe["unit"] != "USD_thousands":
        raise ContractValidationError("case currency/unit contract is invalid")
    increment = parse_decimal(
        recipe["reported_increment"],
        label="preparation_recipe.reported_increment",
        policy=DECIMAL_POLICY,
        positive=True,
        canonical=True,
    )
    if increment != Decimal("1"):
        raise ContractValidationError("reported_increment must equal 1")
    _identifier(recipe["policy_id"], label="preparation_recipe.policy_id")
    _text(recipe["policy_version"], label="preparation_recipe.policy_version")

    sources = _validate_sources(case["sources"])
    source_ids = {str(source["source_id"]) for source in sources}

    balance_periods = [
        _mapping(item, label=f"balance_sheet_periods[{position}]")
        for position, item in enumerate(
            _sequence(
                recipe["balance_sheet_periods"],
                label="preparation_recipe.balance_sheet_periods",
            )
        )
    ]
    cash_periods = [
        _mapping(item, label=f"cash_flow_cumulative_periods[{position}]")
        for position, item in enumerate(
            _sequence(
                recipe["cash_flow_cumulative_periods"],
                label="preparation_recipe.cash_flow_cumulative_periods",
            )
        )
    ]
    if len(balance_periods) != 5 or len(cash_periods) != 4:
        raise ContractValidationError(
            "working-capital fixture requires five stock dates and four flow periods"
        )
    prior_end: date | None = None
    for position, period in enumerate(balance_periods):
        label = f"balance_sheet_periods[{position}]"
        _exact_fields(
            period,
            required=frozenset({"period_label", "period_end", "source_id"}),
            label=label,
        )
        _text(period["period_label"], label=f"{label}.period_label")
        end_text = _iso_date(period["period_end"], label=f"{label}.period_end")
        end = date.fromisoformat(end_text)
        if prior_end is not None and end <= prior_end:
            raise ContractValidationError(
                "balance_sheet_periods must be strictly chronological"
            )
        prior_end = end
        if period["source_id"] not in source_ids:
            raise ContractValidationError(f"{label}.source_id is unknown")
    common_start: str | None = None
    for position, period in enumerate(cash_periods):
        label = f"cash_flow_cumulative_periods[{position}]"
        _exact_fields(
            period,
            required=frozenset(
                {
                    "period_label",
                    "quarter",
                    "period_start",
                    "period_end",
                    "source_id",
                }
            ),
            label=label,
        )
        _text(period["period_label"], label=f"{label}.period_label")
        _identifier(period["quarter"], label=f"{label}.quarter")
        start = _iso_date(period["period_start"], label=f"{label}.period_start")
        end = _iso_date(period["period_end"], label=f"{label}.period_end")
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise ContractValidationError(f"{label} has reversed period bounds")
        if common_start is None:
            common_start = start
        elif start != common_start:
            raise ContractValidationError(
                "cash-flow cumulative periods must share one fiscal-year start"
            )
        if end != str(balance_periods[position + 1]["period_end"]):
            raise ContractValidationError(
                f"{label}.period_end must match the corresponding stock date"
            )
        if period["source_id"] not in source_ids:
            raise ContractValidationError(f"{label}.source_id is unknown")

    fixture_controls = _mapping(case["fixture_controls"], label="fixture_controls")
    _exact_fields(
        fixture_controls,
        required=frozenset(
            {
                "operating_nwc",
                "quarter_bridge",
                "fiscal_year_bridge",
                "tolerance",
            }
        ),
        label="fixture_controls",
    )
    tolerance = parse_decimal(
        fixture_controls["tolerance"],
        label="fixture_controls.tolerance",
        policy=DECIMAL_POLICY,
        non_negative=True,
        canonical=True,
    )
    if tolerance != Decimal("0"):
        raise ContractValidationError("fixture_controls.tolerance must equal 0")
    nwc_controls = [
        _mapping(item, label=f"fixture_controls.operating_nwc[{position}]")
        for position, item in enumerate(
            _sequence(
                fixture_controls["operating_nwc"],
                label="fixture_controls.operating_nwc",
            )
        )
    ]
    bridge_controls = [
        _mapping(item, label=f"fixture_controls.quarter_bridge[{position}]")
        for position, item in enumerate(
            _sequence(
                fixture_controls["quarter_bridge"],
                label="fixture_controls.quarter_bridge",
            )
        )
    ]
    if len(nwc_controls) != len(balance_periods):
        raise ContractValidationError(
            "operating_nwc controls must cover every balance-sheet period"
        )
    if len(bridge_controls) != len(cash_periods):
        raise ContractValidationError(
            "quarter_bridge controls must cover every cash-flow period"
        )
    for position, control in enumerate(nwc_controls):
        label = f"fixture_controls.operating_nwc[{position}]"
        _exact_fields(
            control,
            required=frozenset({"period_end", "value"}),
            label=label,
        )
        if _iso_date(control["period_end"], label=f"{label}.period_end") != str(
            balance_periods[position]["period_end"]
        ):
            raise ContractValidationError(f"{label} is out of sequence")
        parse_decimal(
            control["value"],
            label=f"{label}.value",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
    for position, control in enumerate(bridge_controls):
        label = f"fixture_controls.quarter_bridge[{position}]"
        _exact_fields(
            control,
            required=frozenset(
                {
                    "quarter",
                    "discrete_cash_flow_change",
                    "delta_operating_nwc",
                    "expected_cash_impact",
                    "stock_flow_residual",
                }
            ),
            label=label,
        )
        if control["quarter"] != cash_periods[position]["quarter"]:
            raise ContractValidationError(f"{label}.quarter is out of sequence")
        for field in (
            "discrete_cash_flow_change",
            "delta_operating_nwc",
            "expected_cash_impact",
            "stock_flow_residual",
        ):
            parse_decimal(
                control[field],
                label=f"{label}.{field}",
                policy=DECIMAL_POLICY,
                canonical=True,
            )
    fiscal_control = _mapping(
        fixture_controls["fiscal_year_bridge"],
        label="fixture_controls.fiscal_year_bridge",
    )
    _exact_fields(
        fiscal_control,
        required=frozenset(
            {
                "cumulative_cash_flow_change",
                "delta_operating_nwc",
                "expected_cash_impact",
                "stock_flow_residual",
            }
        ),
        label="fixture_controls.fiscal_year_bridge",
    )
    for field in (
        "cumulative_cash_flow_change",
        "delta_operating_nwc",
        "expected_cash_impact",
        "stock_flow_residual",
    ):
        parse_decimal(
            fiscal_control[field],
            label=f"fixture_controls.fiscal_year_bridge.{field}",
            policy=DECIMAL_POLICY,
            canonical=True,
        )

    files = _mapping(case["files"], label="files")
    _exact_fields(
        files,
        required=frozenset(
            {
                "public_working_capital_facts",
                "reviewed_working_capital_policy",
            }
        ),
        label="files",
    )
    boundary = _mapping(case["disclosure_boundary"], label="disclosure_boundary")
    _exact_fields(
        boundary,
        required=frozenset(
            {
                "publication_status",
                "report_ready",
                "residual_allocation_emitted",
                "row_lineage_declared",
                "semantic_authority",
                "source_authority",
                "statement",
            }
        ),
        label="disclosure_boundary",
    )
    expected_boundary = {
        "publication_status": "withheld",
        "report_ready": False,
        "residual_allocation_emitted": False,
        "row_lineage_declared": False,
        "semantic_authority": "unproven",
        "source_authority": "unproven",
    }
    for field, expected in expected_boundary.items():
        if boundary[field] != expected:
            raise ContractValidationError(
                f"disclosure_boundary.{field} must equal {expected!r}"
            )
    _text(boundary["statement"], label="disclosure_boundary.statement")
    return {
        "recipe": recipe,
        "sources": sources,
        "balance_periods": balance_periods,
        "cash_periods": cash_periods,
        "fixture_controls": fixture_controls,
    }


def _policy_errors(
    policy: Mapping[str, Any],
    recipe: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _exact_fields(
        policy,
        required=frozenset(
            {
                "schema_version",
                "policy_id",
                "policy_version",
                "unit",
                "basis",
                "review",
                "balance_sheet_policy",
                "cash_flow_policy",
                "stock_flow_bridge_policy",
                "caption_boundaries",
                "prohibited_analytics",
            }
        ),
        label="policy",
    )
    if policy["schema_version"] != POLICY_SCHEMA:
        raise ContractValidationError(f"policy.schema_version must be {POLICY_SCHEMA}")
    errors: list[dict[str, Any]] = []
    if (
        policy["policy_id"] != recipe["policy_id"]
        or policy["policy_version"] != recipe["policy_version"]
        or policy["unit"] != recipe["unit"]
    ):
        errors.append(
            _error(
                "policy_review_contract",
                "policy_identity_mismatch",
                "Policy identity, version, and unit must match the case recipe.",
            )
        )
    _text(policy["basis"], label="policy.basis")
    review = _mapping(policy["review"], label="policy.review")
    _exact_fields(
        review,
        required=frozenset({"status", "reviewed_on", "reviewer"}),
        label="policy.review",
    )
    _iso_date(review["reviewed_on"], label="policy.review.reviewed_on")
    _text(review["reviewer"], label="policy.review.reviewer")
    if review["status"] != "reviewed":
        errors.append(
            _error(
                "policy_review_contract",
                "policy_not_reviewed",
                "Working-capital policy must have status reviewed.",
            )
        )

    balance_policy = _mapping(
        policy["balance_sheet_policy"],
        label="policy.balance_sheet_policy",
    )
    _exact_fields(
        balance_policy,
        required=frozenset(
            {
                "metric_id",
                "formula_terms",
                "excluded_fact_keys",
                "control_only_fact_keys",
            }
        ),
        label="policy.balance_sheet_policy",
    )
    if balance_policy["metric_id"] != "operating_nwc":
        errors.append(
            _error(
                "policy_review_contract",
                "metric_id_mismatch",
                "Reviewed balance-sheet metric must be operating_nwc.",
            )
        )
    formula_terms = [
        _mapping(item, label=f"policy.formula_terms[{position}]")
        for position, item in enumerate(
            _sequence(
                balance_policy["formula_terms"],
                label="policy.balance_sheet_policy.formula_terms",
            )
        )
    ]
    balance_formula: list[tuple[str, str]] = []
    for position, term in enumerate(formula_terms):
        _exact_fields(
            term,
            required=frozenset({"fact_key", "multiplier"}),
            label=f"policy.formula_terms[{position}]",
        )
        multiplier = parse_decimal(
            term["multiplier"],
            label=f"policy.formula_terms[{position}].multiplier",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
        balance_formula.append((str(term["fact_key"]), decimal_text(multiplier)))
    if tuple(balance_formula) != EXPECTED_BALANCE_FORMULA:
        errors.append(
            _error(
                "policy_review_contract",
                "operating_nwc_formula_mismatch",
                "Reviewed operating-NWC formula does not match the fixed fixture policy.",
            )
        )
    excluded_rows = [
        _mapping(item, label=f"policy.excluded_fact_keys[{position}]")
        for position, item in enumerate(
            _sequence(
                balance_policy["excluded_fact_keys"],
                label="policy.balance_sheet_policy.excluded_fact_keys",
            )
        )
    ]
    excluded_keys: list[str] = []
    for position, excluded in enumerate(excluded_rows):
        _exact_fields(
            excluded,
            required=frozenset({"fact_key", "reason"}),
            label=f"policy.excluded_fact_keys[{position}]",
        )
        excluded_keys.append(str(excluded["fact_key"]))
        _text(excluded["reason"], label=f"policy.excluded_fact_keys[{position}].reason")
    if tuple(excluded_keys) != EXPECTED_EXCLUDED_KEYS:
        errors.append(
            _error(
                "policy_review_contract",
                "excluded_fact_keys_mismatch",
                "Cash, income taxes payable, and short-term borrowings must remain excluded.",
            )
        )
    if balance_policy["control_only_fact_keys"] != [
        "total_current_assets",
        "total_current_liabilities",
    ]:
        errors.append(
            _error(
                "policy_review_contract",
                "control_only_fact_keys_mismatch",
                "Current-asset and current-liability totals must remain control-only.",
            )
        )

    cash_policy = _mapping(
        policy["cash_flow_policy"],
        label="policy.cash_flow_policy",
    )
    _exact_fields(
        cash_policy,
        required=frozenset(
            {
                "cumulative_component_terms",
                "de_cumulation",
                "source_sign_convention",
            }
        ),
        label="policy.cash_flow_policy",
    )
    cash_terms = [
        _mapping(item, label=f"policy.cash_flow_terms[{position}]")
        for position, item in enumerate(
            _sequence(
                cash_policy["cumulative_component_terms"],
                label="policy.cash_flow_policy.cumulative_component_terms",
            )
        )
    ]
    cash_formula: list[tuple[str, str]] = []
    for position, term in enumerate(cash_terms):
        _exact_fields(
            term,
            required=frozenset({"fact_key", "multiplier"}),
            label=f"policy.cash_flow_terms[{position}]",
        )
        multiplier = parse_decimal(
            term["multiplier"],
            label=f"policy.cash_flow_terms[{position}].multiplier",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
        cash_formula.append((str(term["fact_key"]), decimal_text(multiplier)))
    if tuple(cash_formula) != EXPECTED_CASH_FLOW_FORMULA:
        errors.append(
            _error(
                "policy_review_contract",
                "cash_flow_formula_mismatch",
                "Cash-flow cumulative component formula does not match the reviewed policy.",
            )
        )
    if cash_policy["de_cumulation"] != DE_CUMULATION_METHOD:
        errors.append(
            _error(
                "policy_review_contract",
                "cash_flow_de_cumulation_policy_mismatch",
                "Cash-flow de-cumulation method does not match the reviewed policy.",
            )
        )
    if (
        cash_policy["source_sign_convention"]
        != "cash_impact_native_positive_source_negative_use"
    ):
        errors.append(
            _error(
                "policy_review_contract",
                "cash_flow_sign_convention_mismatch",
                "Cash-flow native sign convention changed.",
            )
        )

    bridge_policy = _mapping(
        policy["stock_flow_bridge_policy"],
        label="policy.stock_flow_bridge_policy",
    )
    _exact_fields(
        bridge_policy,
        required=frozenset(
            {
                "expected_cash_impact_formula",
                "residual_formula",
                "residual_status",
                "force_residual_to_zero",
                "allocate_residual",
            }
        ),
        label="policy.stock_flow_bridge_policy",
    )
    expected_bridge = {
        "expected_cash_impact_formula": "negative_change_in_operating_nwc",
        "residual_formula": ("period_cash_flow_change_minus_expected_cash_impact"),
        "residual_status": "unexplained",
        "force_residual_to_zero": False,
        "allocate_residual": False,
    }
    for field, expected in expected_bridge.items():
        if bridge_policy[field] != expected:
            errors.append(
                _error(
                    "policy_review_contract",
                    "residual_policy_mismatch",
                    "Residual must remain non-zero-capable, unallocated, and unexplained.",
                    (field,),
                )
            )

    boundaries = _mapping(
        policy["caption_boundaries"],
        label="policy.caption_boundaries",
    )
    _exact_fields(
        boundaries,
        required=frozenset(
            {
                "cash_flow_other_assets_equals_balance_sheet_other_current_assets",
                "cash_flow_accounts_payable_and_accrued_liabilities_must_remain_combined",
                "statement",
            }
        ),
        label="policy.caption_boundaries",
    )
    if (
        boundaries["cash_flow_other_assets_equals_balance_sheet_other_current_assets"]
        is not False
        or boundaries[
            "cash_flow_accounts_payable_and_accrued_liabilities_must_remain_combined"
        ]
        is not True
    ):
        errors.append(
            _error(
                "caption_boundary_contract",
                "caption_boundary_mismatch",
                "Unlike captions must remain distinct and the combined cash-flow line must not be split.",
            )
        )
    _text(boundaries["statement"], label="policy.caption_boundaries.statement")
    if tuple(policy["prohibited_analytics"]) != EXPECTED_PROHIBITED_ANALYTICS:
        errors.append(
            _error(
                "policy_review_contract",
                "prohibited_analytics_mismatch",
                "Ratios, targets, and normalization must remain outside this slice.",
            )
        )
    return errors


def _fact_errors(
    rows: Sequence[Mapping[str, str]],
    *,
    recipe: Mapping[str, Any],
    balance_periods: Sequence[Mapping[str, Any]],
    cash_periods: Sequence[Mapping[str, Any]],
    source_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str], Decimal]]:
    errors: list[dict[str, Any]] = []
    fact_ids = [row["fact_id"] for row in rows]
    duplicate_ids = sorted(
        fact_id for fact_id, count in Counter(fact_ids).items() if count > 1
    )
    if duplicate_ids:
        errors.append(
            _error(
                "duplicate_control",
                "duplicate_fact_id",
                "Public facts contain duplicate fact_id values.",
                duplicate_ids,
            )
        )
    if fact_ids != sorted(fact_ids):
        errors.append(
            _error(
                "input_contract",
                "fact_rows_not_sorted",
                "Public facts must be sorted by fact_id.",
            )
        )

    balance_by_end = {str(period["period_end"]): period for period in balance_periods}
    cash_by_end = {str(period["period_end"]): period for period in cash_periods}
    expected_natural_keys = {
        ("balance_sheet_stock", end, fact_key)
        for end in balance_by_end
        for fact_key in BALANCE_SHEET_FACT_KEYS
    } | {
        ("cash_flow_cumulative_change", end, fact_key)
        for end in cash_by_end
        for fact_key in CASH_FLOW_FACT_KEYS
    }
    natural_keys: list[tuple[str, str, str]] = []
    values: dict[tuple[str, str, str], Decimal] = {}
    for position, row in enumerate(rows, start=2):
        row_id = row["fact_id"] or f"row_{position}"
        try:
            _identifier(row["fact_id"], label=f"public facts row {position}.fact_id")
        except ContractValidationError as exc:
            errors.append(
                _error(
                    "input_contract",
                    "invalid_fact_id",
                    str(exc),
                    (row_id,),
                )
            )
        kind = row["fact_kind"]
        end = row["period_end"]
        fact_key = row["fact_key"]
        natural_key = (kind, end, fact_key)
        natural_keys.append(natural_key)
        period_spec: Mapping[str, Any] | None
        expected_keys: tuple[str, ...]
        expected_grain: str
        expected_sign: str
        if kind == "balance_sheet_stock":
            period_spec = balance_by_end.get(end)
            expected_keys = BALANCE_SHEET_FACT_KEYS
            expected_grain = "instant"
            expected_sign = "reported_balance_positive"
        elif kind == "cash_flow_cumulative_change":
            period_spec = cash_by_end.get(end)
            expected_keys = CASH_FLOW_FACT_KEYS
            expected_grain = "cumulative_ytd"
            expected_sign = "cash_impact_native_positive_source_negative_use"
        else:
            period_spec = None
            expected_keys = ()
            expected_grain = ""
            expected_sign = ""
            errors.append(
                _error(
                    "input_contract",
                    "invalid_fact_kind",
                    "Public fact kind is not supported.",
                    (row_id, kind),
                )
            )
        if period_spec is None:
            errors.append(
                _error(
                    "period_contract",
                    "unknown_fact_period",
                    "Public fact period_end is not declared for its fact kind.",
                    (row_id, end),
                )
            )
        else:
            expected_start = (
                end
                if kind == "balance_sheet_stock"
                else str(period_spec["period_start"])
            )
            if (
                row["period_label"] != period_spec["period_label"]
                or row["period_start"] != expected_start
                or row["period_grain"] != expected_grain
            ):
                errors.append(
                    _error(
                        "period_contract",
                        "fact_period_mismatch",
                        "Public fact period fields do not match the case period.",
                        (row_id,),
                    )
                )
            try:
                _iso_date(row["period_start"], label=f"{row_id}.period_start")
                _iso_date(row["period_end"], label=f"{row_id}.period_end")
            except ContractValidationError as exc:
                errors.append(
                    _error(
                        "period_contract",
                        "invalid_fact_date",
                        str(exc),
                        (row_id,),
                    )
                )
            if row["source_id"] != period_spec["source_id"]:
                errors.append(
                    _error(
                        "source_contract",
                        "fact_source_mismatch",
                        "Public fact source does not match its declared period source.",
                        (row_id, row["source_id"]),
                    )
                )
        if fact_key not in expected_keys:
            errors.append(
                _error(
                    "caption_boundary_contract",
                    "unexpected_fact_key",
                    "Public fact key is not allowed for its source statement.",
                    (row_id, fact_key),
                )
            )
        elif row["source_caption"] != SOURCE_CAPTIONS[fact_key]:
            errors.append(
                _error(
                    "caption_boundary_contract",
                    "source_caption_mismatch",
                    "Source caption does not match the pinned statement caption.",
                    (row_id, fact_key),
                )
            )
        if row["unit"] != recipe["unit"]:
            errors.append(
                _error(
                    "unit_contract",
                    "fact_unit_mismatch",
                    "Public fact unit does not match the case unit.",
                    (row_id, row["unit"]),
                )
            )
        if row["source_sign_convention"] != expected_sign:
            errors.append(
                _error(
                    "unit_contract",
                    "fact_sign_convention_mismatch",
                    "Public fact sign convention does not match its fact kind.",
                    (row_id,),
                )
            )
        if row["source_id"] not in source_ids:
            errors.append(
                _error(
                    "source_contract",
                    "unknown_source_id",
                    "Public fact references an undeclared source.",
                    (row_id, row["source_id"]),
                )
            )
        if not row["source_locator"].strip():
            errors.append(
                _error(
                    "source_contract",
                    "missing_source_locator",
                    "Public fact must retain a source locator.",
                    (row_id,),
                )
            )
        try:
            value = parse_decimal(
                row["source_value"],
                label=f"{row_id}.source_value",
                policy=DECIMAL_POLICY,
                canonical=True,
            )
            increment = parse_decimal(
                recipe["reported_increment"],
                label="reported_increment",
                policy=DECIMAL_POLICY,
                positive=True,
                canonical=True,
            )
            if not is_on_increment(value, increment, policy=DECIMAL_POLICY):
                errors.append(
                    _error(
                        "unit_contract",
                        "fact_increment_mismatch",
                        "Public fact is off the declared reporting increment.",
                        (row_id,),
                    )
                )
            if kind == "balance_sheet_stock" and value < 0:
                errors.append(
                    _error(
                        "unit_contract",
                        "negative_balance_sheet_stock",
                        "This fixture requires non-negative balance-sheet stocks.",
                        (row_id,),
                    )
                )
            values.setdefault(natural_key, value)
        except ContractValidationError as exc:
            errors.append(
                _error(
                    "unit_contract",
                    "invalid_source_value",
                    str(exc),
                    (row_id,),
                )
            )

    duplicate_natural = sorted(
        "|".join(key) for key, count in Counter(natural_keys).items() if count > 1
    )
    if duplicate_natural:
        errors.append(
            _error(
                "duplicate_control",
                "duplicate_fact_natural_key",
                "Public facts contain duplicate statement-period-caption keys.",
                duplicate_natural,
            )
        )
    actual_natural_keys = set(natural_keys)
    missing = sorted(
        "|".join(key) for key in expected_natural_keys - actual_natural_keys
    )
    unexpected = sorted(
        "|".join(key) for key in actual_natural_keys - expected_natural_keys
    )
    if missing:
        errors.append(
            _error(
                "input_contract",
                "missing_required_fact",
                "Public facts are missing required statement-period-caption keys.",
                missing,
            )
        )
    if unexpected:
        errors.append(
            _error(
                "input_contract",
                "unexpected_public_fact",
                "Public facts contain unexpected statement-period-caption keys.",
                unexpected,
            )
        )
    return errors, values


def _value(
    values: Mapping[tuple[str, str, str], Decimal],
    kind: str,
    period_end: str,
    fact_key: str,
) -> Decimal:
    try:
        return values[(kind, period_end, fact_key)]
    except KeyError as exc:
        raise ContractValidationError(
            f"required fact is unavailable: {kind}|{period_end}|{fact_key}"
        ) from exc


def _compute_outputs(
    *,
    values: Mapping[tuple[str, str, str], Decimal],
    case_state: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, Any]],
]:
    errors: list[dict[str, Any]] = []
    recipe = case_state["recipe"]
    balance_periods = case_state["balance_periods"]
    cash_periods = case_state["cash_periods"]
    controls = case_state["fixture_controls"]
    policy_id = str(policy["policy_id"])
    unit = str(recipe["unit"])
    balance_terms = policy["balance_sheet_policy"]["formula_terms"]
    cash_terms = policy["cash_flow_policy"]["cumulative_component_terms"]

    schedule_rows: list[dict[str, str]] = []
    nwc_values: list[Decimal] = []
    for position, period in enumerate(balance_periods):
        end = str(period["period_end"])
        cash = _value(values, "balance_sheet_stock", end, "cash_and_cash_equivalents")
        ar_net = _value(
            values,
            "balance_sheet_stock",
            end,
            "trade_and_other_accounts_receivable_net",
        )
        inventory = _value(values, "balance_sheet_stock", end, "inventories")
        other_current_assets = _value(
            values,
            "balance_sheet_stock",
            end,
            "other_current_assets",
        )
        total_current_assets = _value(
            values,
            "balance_sheet_stock",
            end,
            "total_current_assets",
        )
        accounts_payable = _value(
            values,
            "balance_sheet_stock",
            end,
            "accounts_payable",
        )
        accrued_liabilities = _value(
            values,
            "balance_sheet_stock",
            end,
            "accrued_liabilities",
        )
        accrued_payroll = _value(
            values,
            "balance_sheet_stock",
            end,
            "accrued_payroll_and_related_expenses",
        )
        short_term_borrowings = _value(
            values,
            "balance_sheet_stock",
            end,
            "short_term_borrowings",
        )
        income_taxes_payable = _value(
            values,
            "balance_sheet_stock",
            end,
            "income_taxes_payable",
        )
        total_current_liabilities = _value(
            values,
            "balance_sheet_stock",
            end,
            "total_current_liabilities",
        )
        with exact_decimal_context(DECIMAL_POLICY):
            calculated_current_assets = cash + ar_net + inventory + other_current_assets
            calculated_current_liabilities = (
                accounts_payable
                + accrued_liabilities
                + accrued_payroll
                + short_term_borrowings
                + income_taxes_payable
            )
            operating_nwc = sum(
                (
                    _value(
                        values,
                        "balance_sheet_stock",
                        end,
                        str(term["fact_key"]),
                    )
                    * parse_decimal(
                        term["multiplier"],
                        label="balance formula multiplier",
                        policy=DECIMAL_POLICY,
                        canonical=True,
                    )
                    for term in balance_terms
                ),
                Decimal("0"),
            )
        if calculated_current_assets != total_current_assets:
            errors.append(
                _error(
                    "balance_sheet_footing",
                    "current_assets_do_not_foot",
                    "Current-asset components do not equal reported total current assets.",
                    (end,),
                )
            )
        if calculated_current_liabilities != total_current_liabilities:
            errors.append(
                _error(
                    "balance_sheet_footing",
                    "current_liabilities_do_not_foot",
                    "Current-liability components do not equal reported total current liabilities.",
                    (end,),
                )
            )
        expected_nwc = parse_decimal(
            controls["operating_nwc"][position]["value"],
            label=f"operating_nwc control {end}",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
        if operating_nwc != expected_nwc:
            errors.append(
                _error(
                    "fixture_control_tie_out",
                    "operating_nwc_control_mismatch",
                    "Calculated operating NWC does not match the pinned fixture control.",
                    (end,),
                )
            )
        nwc_values.append(operating_nwc)
        prior_end = (
            "" if position == 0 else str(balance_periods[position - 1]["period_end"])
        )
        if position == 0:
            delta = ""
            expected_cash = ""
        else:
            with exact_decimal_context(DECIMAL_POLICY):
                delta_value = operating_nwc - nwc_values[position - 1]
                expected_cash_value = -delta_value
                recomputed_current = nwc_values[position - 1] + delta_value
            if recomputed_current != operating_nwc:
                errors.append(
                    _error(
                        "stock_roll_forward",
                        "stock_roll_forward_failed",
                        "Prior operating NWC plus change does not equal current operating NWC.",
                        (end,),
                    )
                )
            delta = decimal_text(delta_value)
            expected_cash = decimal_text(expected_cash_value)
        schedule_rows.append(
            {
                "period_label": str(period["period_label"]),
                "period_end": end,
                "ar_net": decimal_text(ar_net),
                "inventory": decimal_text(inventory),
                "other_current_assets": decimal_text(other_current_assets),
                "accounts_payable": decimal_text(accounts_payable),
                "accrued_liabilities": decimal_text(accrued_liabilities),
                "accrued_payroll": decimal_text(accrued_payroll),
                "operating_nwc": decimal_text(operating_nwc),
                "prior_period_end": prior_end,
                "delta_operating_nwc": delta,
                "expected_cash_impact": expected_cash,
                "unit": unit,
                "policy_id": policy_id,
            }
        )

    cumulative_values: list[Decimal] = []
    cumulative_components: list[dict[str, Decimal]] = []
    discrete_values: list[Decimal] = []
    discrete_rows: list[dict[str, str]] = []
    for position, period in enumerate(cash_periods):
        end = str(period["period_end"])
        discrete_period_start = (
            str(period["period_start"])
            if position == 0
            else (
                date.fromisoformat(str(cash_periods[position - 1]["period_end"]))
                + timedelta(days=1)
            ).isoformat()
        )
        component_values = {
            str(term["fact_key"]): (
                _value(
                    values,
                    "cash_flow_cumulative_change",
                    end,
                    str(term["fact_key"]),
                )
                * parse_decimal(
                    term["multiplier"],
                    label="cash-flow formula multiplier",
                    policy=DECIMAL_POLICY,
                    canonical=True,
                )
            )
            for term in cash_terms
        }
        prior_components = (
            {fact_key: Decimal("0") for fact_key in component_values}
            if position == 0
            else cumulative_components[position - 1]
        )
        with exact_decimal_context(DECIMAL_POLICY):
            cumulative = sum(component_values.values(), Decimal("0"))
            prior_cumulative = (
                Decimal("0") if position == 0 else cumulative_values[position - 1]
            )
            discrete = cumulative - prior_cumulative
            discrete_components = {
                fact_key: value - prior_components[fact_key]
                for fact_key, value in component_values.items()
            }
            recombined = prior_cumulative + discrete
            component_sum = sum(discrete_components.values(), Decimal("0"))
        if recombined != cumulative:
            errors.append(
                _error(
                    "cash_flow_de_cumulation",
                    "cash_flow_recombination_failed",
                    "Prior cumulative cash flow plus the discrete quarter does not recombine.",
                    (str(period["quarter"]),),
                )
            )
        if component_sum != discrete:
            errors.append(
                _error(
                    "cash_flow_de_cumulation",
                    "cash_flow_component_sum_failed",
                    "Discrete cash-flow components do not sum to the discrete quarter.",
                    (str(period["quarter"]),),
                )
            )
        cumulative_values.append(cumulative)
        cumulative_components.append(component_values)
        discrete_values.append(discrete)
        discrete_rows.append(
            {
                "quarter": str(period["quarter"]),
                "period_start": discrete_period_start,
                "period_end": end,
                "trade_and_other_accounts_receivable_change": decimal_text(
                    discrete_components["trade_and_other_accounts_receivable"]
                ),
                "inventory_change": decimal_text(discrete_components["inventories"]),
                "other_assets_change": decimal_text(
                    discrete_components["other_assets"]
                ),
                "accounts_payable_and_accrued_liabilities_change": decimal_text(
                    discrete_components["accounts_payable_and_accrued_liabilities"]
                ),
                "accrued_payroll_and_related_expenses_change": decimal_text(
                    discrete_components["accrued_payroll_and_related_expenses"]
                ),
                "cumulative_cash_flow_change": decimal_text(cumulative),
                "prior_cumulative_cash_flow_change": decimal_text(prior_cumulative),
                "discrete_cash_flow_change": decimal_text(discrete),
                "unit": unit,
                "source_sign_convention": (
                    "cash_impact_native_positive_source_negative_use"
                ),
                "current_cumulative_source_id": str(period["source_id"]),
                "prior_cumulative_source_id": (
                    ""
                    if position == 0
                    else str(cash_periods[position - 1]["source_id"])
                ),
                "policy_id": policy_id,
            }
        )
    with exact_decimal_context(DECIMAL_POLICY):
        if sum(discrete_values, Decimal("0")) != cumulative_values[-1]:
            errors.append(
                _error(
                    "cash_flow_de_cumulation",
                    "cash_flow_full_year_recombination_failed",
                    "Discrete quarters do not sum to the fiscal-year cumulative cash flow.",
                )
            )

    bridge_rows: list[dict[str, str]] = []
    residuals: list[Decimal] = []
    for position, period in enumerate(cash_periods):
        quarter = str(period["quarter"])
        control = controls["quarter_bridge"][position]
        with exact_decimal_context(DECIMAL_POLICY):
            delta_nwc = nwc_values[position + 1] - nwc_values[position]
            expected_cash_impact = -delta_nwc
            residual = discrete_values[position] - expected_cash_impact
        expected_values = {
            "discrete_cash_flow_change": discrete_values[position],
            "delta_operating_nwc": delta_nwc,
            "expected_cash_impact": expected_cash_impact,
            "stock_flow_residual": residual,
        }
        for field, actual in expected_values.items():
            expected = parse_decimal(
                control[field],
                label=f"{quarter}.{field} control",
                policy=DECIMAL_POLICY,
                canonical=True,
            )
            if actual != expected:
                errors.append(
                    _error(
                        "fixture_control_tie_out",
                        "quarter_bridge_control_mismatch",
                        "Calculated quarter bridge does not match the pinned fixture control.",
                        (quarter, field),
                    )
                )
        residuals.append(residual)
        bridge_rows.append(
            {
                "bridge_row_id": quarter,
                "row_kind": "quarter",
                "period_start": discrete_rows[position]["period_start"],
                "period_end": str(period["period_end"]),
                "cumulative_cash_flow_change": decimal_text(
                    cumulative_values[position]
                ),
                "prior_cumulative_cash_flow_change": decimal_text(
                    Decimal("0") if position == 0 else cumulative_values[position - 1]
                ),
                "period_cash_flow_change": decimal_text(discrete_values[position]),
                "delta_operating_nwc": decimal_text(delta_nwc),
                "expected_cash_impact": decimal_text(expected_cash_impact),
                "stock_flow_residual": decimal_text(residual),
                "residual_status": "unexplained",
                "unit": unit,
                "policy_id": policy_id,
            }
        )
    with exact_decimal_context(DECIMAL_POLICY):
        fiscal_delta_nwc = nwc_values[-1] - nwc_values[0]
        fiscal_expected_cash = -fiscal_delta_nwc
        fiscal_residual = cumulative_values[-1] - fiscal_expected_cash
        residual_sum = sum(residuals, Decimal("0"))
    if residual_sum != fiscal_residual:
        errors.append(
            _error(
                "stock_flow_bridge",
                "residual_roll_forward_failed",
                "Quarter residuals do not sum to the fiscal-year residual.",
            )
        )
    fiscal_control = controls["fiscal_year_bridge"]
    fiscal_values = {
        "cumulative_cash_flow_change": cumulative_values[-1],
        "delta_operating_nwc": fiscal_delta_nwc,
        "expected_cash_impact": fiscal_expected_cash,
        "stock_flow_residual": fiscal_residual,
    }
    for field, actual in fiscal_values.items():
        expected = parse_decimal(
            fiscal_control[field],
            label=f"fiscal_year_bridge.{field} control",
            policy=DECIMAL_POLICY,
            canonical=True,
        )
        if actual != expected:
            errors.append(
                _error(
                    "fixture_control_tie_out",
                    "fiscal_bridge_control_mismatch",
                    "Calculated fiscal-year bridge does not match the pinned fixture control.",
                    (field,),
                )
            )
    bridge_rows.append(
        {
            "bridge_row_id": "FY2025",
            "row_kind": "fiscal_year",
            "period_start": str(cash_periods[0]["period_start"]),
            "period_end": str(cash_periods[-1]["period_end"]),
            "cumulative_cash_flow_change": decimal_text(cumulative_values[-1]),
            "prior_cumulative_cash_flow_change": "",
            "period_cash_flow_change": decimal_text(cumulative_values[-1]),
            "delta_operating_nwc": decimal_text(fiscal_delta_nwc),
            "expected_cash_impact": decimal_text(fiscal_expected_cash),
            "stock_flow_residual": decimal_text(fiscal_residual),
            "residual_status": "unexplained",
            "unit": unit,
            "policy_id": policy_id,
        }
    )
    return schedule_rows, discrete_rows, bridge_rows, errors


def _write_csv(
    path: Path,
    *,
    columns: tuple[str, ...],
    rows: Sequence[Mapping[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _checks(
    errors: Sequence[Mapping[str, Any]],
    *,
    ran_checks: set[str],
) -> list[dict[str, Any]]:
    counts = Counter(str(error["gate"]) for error in errors)
    return [
        {
            "check_id": check_id,
            "status": (
                "not_run"
                if check_id not in ran_checks
                else ("failed" if counts[check_id] else "passed")
            ),
            "failure_count": counts[check_id],
        }
        for check_id in CHECK_IDS
    ]


def _source_receipts(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "source_id": source["source_id"],
                "title": source["title"],
                "form": source["form"],
                "accession": source["accession"],
                "filed_date": source["filed_date"],
                "url": source["url"],
                "byte_count": source["byte_count"],
                "sha256": source["sha256"],
                "receipt_scope": "declared_remote_receipt",
            }
            for source in sources
        ],
        key=lambda item: str(item["source_id"]),
    )


def _reconciliation(
    *,
    case: Mapping[str, Any],
    case_state: Mapping[str, Any],
    facts_path: Path,
    policy_path: Path,
    rows: Sequence[Mapping[str, str]],
    errors: Sequence[Mapping[str, Any]],
    ran_checks: set[str],
    success_outputs: bool,
) -> dict[str, Any]:
    sorted_errors = sorted(
        [dict(error) for error in errors],
        key=lambda item: (
            str(item["gate"]),
            str(item["code"]),
            tuple(item["identifiers"]),
        ),
    )
    balance_count = sum(row["fact_kind"] == "balance_sheet_stock" for row in rows)
    cash_count = sum(row["fact_kind"] == "cash_flow_cumulative_change" for row in rows)
    return {
        "schema_version": RECONCILIATION_SCHEMA,
        "case_id": case["case_id"],
        "status": "failed" if sorted_errors else "passed",
        "publication_status": "withheld",
        "report_ready": False,
        "row_lineage_declared": False,
        "semantic_authority": "unproven",
        "source_authority": "unproven",
        "inputs": {
            "public_working_capital_facts": {
                "path": facts_path.name,
                "byte_count": facts_path.stat().st_size,
                "sha256": file_sha256(facts_path),
            },
            "reviewed_working_capital_policy": {
                "path": policy_path.name,
                "byte_count": policy_path.stat().st_size,
                "sha256": file_sha256(policy_path),
            },
        },
        "engine": {
            "producer": Path(__file__).name,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": file_sha256(Path(__file__).resolve()),
            "recipe_id": case_state["recipe"]["recipe_id"],
            "arithmetic": "decimal_exact",
        },
        "counts": {
            "raw_fact_rows": len(rows),
            "balance_sheet_fact_rows": balance_count,
            "cash_flow_fact_rows": cash_count,
            "balance_sheet_periods": len(case_state["balance_periods"]),
            "cash_flow_cumulative_periods": len(case_state["cash_periods"]),
            "schedule_rows": (
                len(case_state["balance_periods"]) if success_outputs else 0
            ),
            "discrete_cash_flow_rows": (
                len(case_state["cash_periods"]) if success_outputs else 0
            ),
            "bridge_rows": (
                len(case_state["cash_periods"]) + 1 if success_outputs else 0
            ),
            "exception_rows": len(sorted_errors),
            "errors": len(sorted_errors),
        },
        "checks": _checks(sorted_errors, ran_checks=ran_checks),
        "errors": sorted_errors,
        "residual_treatment": {
            "force_to_zero": False,
            "allocation_emitted": False,
            "status": "unexplained",
        },
        "caption_boundaries": {
            "cash_flow_other_assets_is_balance_sheet_other_current_assets": False,
            "cash_flow_ap_and_accrued_split": False,
        },
        "outputs_emitted": (
            list(PRODUCER_OUTPUT_NAMES)
            if success_outputs
            else [
                "exceptions.csv",
                "raw_fact_preservation.csv",
                "reconciliation.json",
            ]
        ),
    }


def _artifact_receipt(path: Path, artifact_id: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _manifest(
    *,
    case: Mapping[str, Any],
    case_state: Mapping[str, Any],
    facts_path: Path,
    policy_path: Path,
    output_dir: Path,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    outputs = sorted(
        [
            _artifact_receipt(
                output_dir / "discrete_cash_flow_schedule.csv",
                "discrete_cash_flow_schedule",
            ),
            _artifact_receipt(
                output_dir / "exceptions.csv",
                "exceptions",
            ),
            _artifact_receipt(
                output_dir / "raw_fact_preservation.csv",
                "raw_fact_preservation",
            ),
            _artifact_receipt(
                output_dir / "reconciliation.json",
                "reconciliation",
            ),
            _artifact_receipt(
                output_dir / "stock_flow_bridge.csv",
                "stock_flow_bridge",
            ),
            _artifact_receipt(
                output_dir / "working_capital_schedule.csv",
                "working_capital_schedule",
            ),
        ],
        key=lambda item: str(item["artifact_id"]),
    )
    return {
        "schema_version": MANIFEST_SCHEMA,
        "case_id": case["case_id"],
        "preparation_status": "passed",
        "publication_status": "withheld",
        "report_ready": False,
        "recipe": {
            "recipe_id": case_state["recipe"]["recipe_id"],
            "engine_version": ENGINE_VERSION,
            "engine_sha256": file_sha256(Path(__file__).resolve()),
            "arithmetic": "decimal_exact",
            "unit": case_state["recipe"]["unit"],
        },
        "inputs": {
            "public_working_capital_facts": {
                "path": facts_path.name,
                "byte_count": facts_path.stat().st_size,
                "sha256": file_sha256(facts_path),
            },
            "reviewed_working_capital_policy": {
                "path": policy_path.name,
                "byte_count": policy_path.stat().st_size,
                "sha256": file_sha256(policy_path),
                "policy_id": policy["policy_id"],
                "policy_version": policy["policy_version"],
                "review_status": policy["review"]["status"],
                "reviewed_on": policy["review"]["reviewed_on"],
                "reviewer": policy["review"]["reviewer"],
            },
        },
        "source_receipts": _source_receipts(case_state["sources"]),
        "outputs": outputs,
        "canonical_output_set_sha256": canonical_json_sha256(outputs),
        "raw_fact_preservation": {
            "byte_identical_to_input": (
                (output_dir / "raw_fact_preservation.csv").read_bytes()
                == facts_path.read_bytes()
            ),
            "source_sha256": file_sha256(facts_path),
            "output_sha256": file_sha256(output_dir / "raw_fact_preservation.csv"),
        },
        "lineage": {
            "artifact_lineage_declared": True,
            "row_lineage_declared": False,
            "row_lineage_records": [],
            "limitation": (
                "Artifacts and aggregate formulas are pinned, but no output row "
                "claims source-row lineage authority."
            ),
        },
        "boundaries": {
            "semantic_authority": "unproven",
            "source_authority": "unproven",
            "cash_flow_other_assets_is_balance_sheet_other_current_assets": False,
            "cash_flow_ap_and_accrued_split": False,
            "residual_allocation_emitted": False,
            "residual_status": "unexplained",
            "prohibited_analytics_emitted": [],
        },
    }


def prepare_working_capital_case(
    case_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the reviewed working-capital fixture and return its reconciliation."""

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in PRODUCER_OUTPUT_NAMES:
        (output_dir / name).unlink(missing_ok=True)
    unexpected_entries = sorted(path.name for path in output_dir.iterdir())
    if unexpected_entries:
        raise ContractValidationError(
            "output directory must be dedicated to this producer; "
            f"unregistered entries: {', '.join(unexpected_entries)}"
        )

    case_path = Path(case_path).resolve()
    case_root = case_path.parent
    case = strict_json_load(case_path)
    case_state = _validate_case_shape(case)
    facts_path = _validate_file_receipt(
        case_root,
        case["files"]["public_working_capital_facts"],
        label="public_working_capital_facts",
    )
    policy_path = _validate_file_receipt(
        case_root,
        case["files"]["reviewed_working_capital_policy"],
        label="reviewed_working_capital_policy",
    )
    policy = strict_json_load(policy_path)
    rows = read_exact_csv(
        facts_path,
        columns=PUBLIC_FACT_COLUMNS,
        label="public working-capital facts",
    )

    raw_output = output_dir / "raw_fact_preservation.csv"
    raw_output.write_bytes(facts_path.read_bytes())

    errors = _policy_errors(policy, case_state["recipe"])
    fact_validation_errors, values = _fact_errors(
        rows,
        recipe=case_state["recipe"],
        balance_periods=case_state["balance_periods"],
        cash_periods=case_state["cash_periods"],
        source_ids={str(source["source_id"]) for source in case_state["sources"]},
    )
    errors.extend(fact_validation_errors)
    ran_checks = {
        "caption_boundary_contract",
        "duplicate_control",
        "input_contract",
        "period_contract",
        "policy_review_contract",
        "raw_fact_preservation",
        "source_contract",
        "unit_contract",
    }
    if raw_output.read_bytes() != facts_path.read_bytes():
        errors.append(
            _error(
                "raw_fact_preservation",
                "raw_fact_preservation_failed",
                "Raw fact output is not byte-identical to the pinned input.",
            )
        )

    schedule_rows: list[dict[str, str]] = []
    discrete_rows: list[dict[str, str]] = []
    bridge_rows: list[dict[str, str]] = []
    if not errors:
        (
            schedule_rows,
            discrete_rows,
            bridge_rows,
            calculation_errors,
        ) = _compute_outputs(
            values=values,
            case_state=case_state,
            policy=policy,
        )
        errors.extend(calculation_errors)
        ran_checks.update(
            {
                "balance_sheet_footing",
                "cash_flow_de_cumulation",
                "fixture_control_tie_out",
                "operating_nwc_schedule",
                "stock_flow_bridge",
                "stock_roll_forward",
            }
        )

    errors.sort(
        key=lambda item: (
            str(item["gate"]),
            str(item["code"]),
            str(item["message"]),
            tuple(item["identifiers"]),
        )
    )
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
    _write_csv(
        output_dir / "exceptions.csv",
        columns=EXCEPTION_COLUMNS,
        rows=exception_rows,
    )
    passed = not errors
    if passed:
        _write_csv(
            output_dir / "working_capital_schedule.csv",
            columns=SCHEDULE_COLUMNS,
            rows=schedule_rows,
        )
        _write_csv(
            output_dir / "discrete_cash_flow_schedule.csv",
            columns=DISCRETE_CASH_FLOW_COLUMNS,
            rows=discrete_rows,
        )
        _write_csv(
            output_dir / "stock_flow_bridge.csv",
            columns=BRIDGE_COLUMNS,
            rows=bridge_rows,
        )
    reconciliation = _reconciliation(
        case=case,
        case_state=case_state,
        facts_path=facts_path,
        policy_path=policy_path,
        rows=rows,
        errors=errors,
        ran_checks=ran_checks,
        success_outputs=passed,
    )
    write_json(output_dir / "reconciliation.json", reconciliation)
    if passed:
        manifest = _manifest(
            case=case,
            case_state=case_state,
            facts_path=facts_path,
            policy_path=policy_path,
            output_dir=output_dir,
            policy=policy,
        )
        write_json(output_dir / "prepared_evidence_manifest.json", manifest)
    return reconciliation


def main(argv: Sequence[str] | None = None) -> int:
    """Run the working-capital preparation CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = prepare_working_capital_case(args.case, args.output_dir)
    except (ContractValidationError, KeyError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "Working-capital preparation %s: %s",
        result["case_id"],
        result["status"],
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
