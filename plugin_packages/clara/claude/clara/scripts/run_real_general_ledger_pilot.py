#!/usr/bin/env python3
"""Run one reviewer-bounded, mechanical general-ledger preparation pilot.

This producer does not infer an account hierarchy, statement mapping, calendar,
scope, currency, unit, FX treatment, sign convention, tolerance, or output
grain. It applies only the exact decisions in a replay-validated case contract.
The authorization and semantic receipts are replay-validated before source
workbook bytes are hashed or passed to the injected parser.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
from typing import Any, Literal, Protocol

from parse_commercial_general_journal import (
    load_general_journal_layout_contract,
    parse_commercial_general_journal,
)
from preparation_contract_kernel import (
    ContractValidationError,
    decimal_text,
    file_sha256,
    file_snapshot_beneath,
    parse_decimal,
    strict_json_snapshot_beneath,
    write_json,
)
from real_data_pilot_output_boundary import (
    create_fresh_pilot_output_directory,
    seal_pilot_output_directory,
)
from validate_real_data_pilot_intake import (
    INTAKE_RECEIPT_SCHEMA_V2,
    PILOT_ID_PATTERN,
    REQUIRED_SEMANTIC_REVIEWS,
    validate_real_data_pilot_intake_receipt_v2,
    validate_real_data_pilot_intake_v2,
)
from validate_real_data_pilot_mechanical_errors import (
    BINDING_FIELDS,
)
from validate_real_data_pilot_mechanical_errors import (
    LIMITATIONS as MECHANICAL_LIMITATIONS,
)
from validate_real_data_pilot_mechanical_errors import (
    MECHANICAL_CLASSES,
    output_receipt_closure_sha256,
    validate_real_data_pilot_mechanical_error_register,
)
from validate_real_data_pilot_semantic_review import (
    SEMANTIC_REVIEW_RECEIPT_SCHEMA,
    validate_real_data_pilot_semantic_review,
    validate_real_data_pilot_semantic_review_receipt,
)

__all__ = [
    "ACCOUNT_MONTH_ROLE",
    "CASE_SCHEMA_VERSION",
    "Movement",
    "MovementParser",
    "ParsedMovementBatch",
    "ParserMechanicalError",
    "PilotRunResult",
    "RECONCILIATION_ROLE",
    "SEMANTIC_DECISIONS_SCHEMA_PATH",
    "SEMANTIC_DECISIONS_SCHEMA_VERSION",
    "parse_reviewed_commercial_general_journal",
    "producer_contract_sha256",
    "run_real_general_ledger_pilot",
]

CASE_SCHEMA_VERSION = "clara.real_general_ledger_preparation_case.v1"
CASE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "real_general_ledger_preparation_case.v1.schema.json"
)
SEMANTIC_DECISIONS_SCHEMA_VERSION = "clara.real_general_ledger_semantic_decisions.v1"
SEMANTIC_DECISIONS_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "real_general_ledger_semantic_decisions.v1.schema.json"
)
GENERAL_JOURNAL_PARSER_PATH = (
    Path(__file__).resolve().with_name("parse_commercial_general_journal.py")
)
MECHANICAL_REGISTER_SCHEMA = "clara.real_data_pilot_mechanical_error_register.v1"
ACCOUNT_MONTH_ROLE = "artifact-18a1a04ef514e9b7"
RECONCILIATION_ROLE = "artifact-4e6ddbf04725f67f"
MECHANICAL_ROLE = "mechanical_errors"
SUCCESS_ROLES = {
    ACCOUNT_MONTH_ROLE: f"artifacts/{ACCOUNT_MONTH_ROLE}.bin",
    RECONCILIATION_ROLE: f"artifacts/{RECONCILIATION_ROLE}.bin",
    MECHANICAL_ROLE: "mechanical_errors.json",
}
FAILURE_ROLES = {MECHANICAL_ROLE: "mechanical_errors.json"}
EXECUTION_ID_PATTERN = re.compile(r"^execution-[0-9a-f]{16}$")
SOURCE_ID_PATTERN = re.compile(r"^source-[0-9a-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Movement:
    """One parser-produced, source-presented debit/credit movement."""

    movement_id: str
    posting_date: date
    source_account_code: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class ParsedMovementBatch:
    """One exact source-bound parser result with separately extracted controls."""

    source_sha256: str
    movements: tuple[Movement, ...]
    source_control_debit: Decimal
    source_control_credit: Decimal


class MovementParser(Protocol):
    """Parser seam used after the receipt and semantic gates have passed."""

    def __call__(
        self,
        source_path: Path,
        *,
        expected_source_sha256: str,
        parser_layout_path: Path,
        expected_parser_layout_sha256: str,
    ) -> ParsedMovementBatch:
        """Return source-presented movements without interpreting them."""


class ParserMechanicalError(ValueError):
    """Signal a fixed parser/source-structure failure without output prose."""


def parse_reviewed_commercial_general_journal(
    source_path: Path,
    *,
    expected_source_sha256: str,
    parser_layout_path: Path,
    expected_parser_layout_sha256: str,
) -> ParsedMovementBatch:
    """Adapt the exact reviewed parser to the producer movement seam."""

    layout_contract = load_general_journal_layout_contract(
        parser_layout_path,
        expected_contract_sha256=expected_parser_layout_sha256,
    )
    parsed = parse_commercial_general_journal(
        source_path,
        expected_source_sha256=expected_source_sha256,
        layout_contract=layout_contract,
    )
    return ParsedMovementBatch(
        source_sha256=parsed.source_sha256,
        movements=tuple(
            Movement(
                movement_id=str(movement.line_id),
                posting_date=movement.posting_date,
                source_account_code=movement.account_code,
                debit=movement.debit,
                credit=movement.credit,
            )
            for movement in parsed.movements
        ),
        source_control_debit=parsed.source_control_debit_total,
        source_control_credit=parsed.source_control_credit_total,
    )


@dataclass(frozen=True)
class PilotRunResult:
    """Sanitized producer result; detailed values remain in the private leaf."""

    status: Literal["failed", "passed"]
    output_directory: Path
    output_receipts: tuple[dict[str, Any], ...]
    failure_code: str | None


@dataclass(frozen=True)
class _ProducerFailure(ValueError):
    check_key: str
    error_key: str


@dataclass(frozen=True)
class _CheckSpec:
    key: str
    mechanical_class: str
    error_keys: tuple[str, ...]


CHECK_SPECS = (
    _CheckSpec(
        "contract",
        "contract",
        (
            "case_or_binding_invalid",
            "intake_receipt_invalid",
            "semantic_receipt_invalid",
            "semantic_review_blocked",
        ),
    ),
    _CheckSpec(
        "source",
        "replay",
        ("source_receipt_mismatch",),
    ),
    _CheckSpec(
        "parser",
        "source_structure",
        (
            "empty_movement_set",
            "parser_mechanical_failure",
        ),
    ),
    _CheckSpec(
        "movement_identity",
        "source_structure",
        (
            "duplicate_movement_id",
            "invalid_movement_sequence",
            "invalid_source_account_identity",
        ),
    ),
    _CheckSpec(
        "period",
        "period",
        ("posting_date_outside_reviewed_year",),
    ),
    _CheckSpec(
        "numeric",
        "numeric",
        ("invalid_decimal_or_source_sign",),
    ),
    _CheckSpec(
        "reconciliation",
        "reconciliation",
        (
            "monthly_balance_mismatch",
            "reported_control_mismatch",
            "source_control_mismatch",
        ),
    ),
    _CheckSpec(
        "month_coverage",
        "period",
        ("calendar_month_coverage_mismatch",),
    ),
    _CheckSpec(
        "output",
        "output_integrity",
        ("output_bytes_not_sealed",),
    ),
)


def _opaque_id(prefix: str, label: str) -> str:
    digest = hashlib.sha256(
        f"clara.real-general-ledger-pilot.v1:{label}".encode("utf-8")
    ).hexdigest()
    return f"{prefix}-{digest[:16]}"


CHECK_IDS = {spec.key: _opaque_id("check", spec.key) for spec in CHECK_SPECS}
ERROR_CODES = {
    error_key: _opaque_id("code", error_key)
    for spec in CHECK_SPECS
    for error_key in spec.error_keys
}


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    label: str,
) -> None:
    missing = sorted(required - set(value))
    unexpected = sorted(set(value) - required)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(
            f"{label} contains unexpected fields: {unexpected}"
        )


def _constant(value: Any, *, expected: Any, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise ContractValidationError(f"{label} must equal {expected!r}")


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContractValidationError(
            f"{label} must be canonical non-empty text without edge whitespace"
        )
    return value


def _digest(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _opaque_identifier(
    value: Any,
    *,
    pattern: re.Pattern[str],
    label: str,
) -> str:
    result = _text(value, label=label)
    if pattern.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be an opaque digest-shaped ID")
    return result


def _bootstrap_case_identity(case: Mapping[str, Any]) -> tuple[str, str]:
    pilot_id = _opaque_identifier(
        case.get("pilot_id"),
        pattern=PILOT_ID_PATTERN,
        label="case.pilot_id",
    )
    execution_id = _opaque_identifier(
        case.get("execution_id"),
        pattern=EXECUTION_ID_PATTERN,
        label="case.execution_id",
    )
    return pilot_id, execution_id


def _validate_reviewed_projection(
    *,
    reviewed_period_value: Any,
    reviewed_decisions_value: Any,
    reported_controls_value: Any,
    label: str,
) -> None:
    """Enforce only review-projected facts with exact, auditable comparisons."""

    reviewed_period = _mapping(
        reviewed_period_value,
        label=f"{label}.reviewed_period",
    )
    _exact_fields(
        reviewed_period,
        required=frozenset({"year"}),
        label=f"{label}.reviewed_period",
    )
    year = reviewed_period["year"]
    if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2200:
        raise ContractValidationError(
            f"{label}.reviewed_period.year must be an integer from 1900 through 2200"
        )

    decisions = _mapping(
        reviewed_decisions_value,
        label=f"{label}.reviewed_decisions",
    )
    _exact_fields(
        decisions,
        required=frozenset(
            {
                "account_identity",
                "period",
                "scope",
                "currency_unit_fx",
                "sign_convention",
                "control_basis",
                "tolerance",
                "output_grain",
            }
        ),
        label=f"{label}.reviewed_decisions",
    )
    nested_decisions = (
        (
            "account_identity",
            {
                "basis": "source_account_code",
                "normalization": "remove_whitespace_within_reviewed_account_code",
                "statement_mapping": "not_performed",
            },
        ),
        (
            "period",
            {
                "basis": "posting_date",
                "calendar": "gregorian",
                "grain": "calendar_month",
                "date_assignment": "nondecreasing_carried_forward_posting_date",
            },
        ),
        (
            "scope",
            {
                "dataset": "one_source_presented_export",
                "eliminations": "none_applied",
                "entity_basis": "export_level_source_scope_not_emitted",
                "consolidation_status": "not_assessed",
            },
        ),
        (
            "currency_unit_fx",
            {
                "unit": "source_native_unit",
                "fx": "none",
                "currency": "not_asserted",
            },
        ),
    )
    for decision_id, expected in nested_decisions:
        decision = _mapping(
            decisions[decision_id],
            label=f"{label}.reviewed_decisions.{decision_id}",
        )
        _exact_fields(
            decision,
            required=frozenset(expected),
            label=f"{label}.reviewed_decisions.{decision_id}",
        )
        for field, expected_value in expected.items():
            _constant(
                decision[field],
                expected=expected_value,
                label=f"{label}.reviewed_decisions.{decision_id}.{field}",
            )
    for field, expected in (
        ("sign_convention", "debit_positive_credit_negative"),
        (
            "control_basis",
            "exact_extracted_final_debit_and_credit_controls",
        ),
        ("tolerance", "0"),
        ("output_grain", "source_account_x_calendar_month"),
    ):
        _constant(
            decisions[field],
            expected=expected,
            label=f"{label}.reviewed_decisions.{field}",
        )

    controls = _mapping(
        reported_controls_value,
        label=f"{label}.reported_controls",
    )
    _exact_fields(
        controls,
        required=frozenset(
            {
                "debit",
                "credit",
                "journal_balance_required",
                "monthly_balance_required",
                "expected_calendar_months",
            }
        ),
        label=f"{label}.reported_controls",
    )
    parsed_controls = {}
    for field in ("debit", "credit"):
        parsed_controls[field] = parse_decimal(
            controls[field],
            label=f"{label}.reported_controls.{field}",
            non_negative=True,
            canonical=True,
        )
    _constant(
        controls["journal_balance_required"],
        expected=True,
        label=f"{label}.reported_controls.journal_balance_required",
    )
    _constant(
        controls["monthly_balance_required"],
        expected=True,
        label=f"{label}.reported_controls.monthly_balance_required",
    )
    expected_months = controls["expected_calendar_months"]
    if (
        not isinstance(expected_months, list)
        or not 1 <= len(expected_months) <= 12
        or any(not isinstance(month, str) for month in expected_months)
    ):
        raise ContractValidationError(
            f"{label}.reported_controls.expected_calendar_months "
            "must contain 1 through 12 month strings"
        )
    if expected_months != sorted(set(expected_months)):
        raise ContractValidationError(
            f"{label}.reported_controls.expected_calendar_months "
            "must be sorted and unique"
        )
    if any(
        re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", month) is None
        or not month.startswith(f"{year:04d}-")
        for month in expected_months
    ):
        raise ContractValidationError(
            f"{label}.reported_controls.expected_calendar_months "
            "must be exact months in the reviewed year"
        )
    if parsed_controls["debit"] != parsed_controls["credit"]:
        raise ContractValidationError(
            f"{label} reported journal debit and credit controls must be equal"
        )


def _validate_case(
    value: Any,
    *,
    case_sha256: str,
    intake_receipt_sha256: str,
    semantic_receipt_sha256: str,
    semantic_decisions_sha256: str,
    parser_layout_path: Path,
    parser_adapter_implementation_path: Path,
    parser_implementation_path: Path,
    parser: MovementParser,
) -> dict[str, Any]:
    case = _mapping(value, label="case")
    _exact_fields(
        case,
        required=frozenset(
            {
                "schema_version",
                "pilot_id",
                "execution_id",
                "case_status",
                "reviewer_role",
                "source",
                "bindings",
                "reviewed_period",
                "reviewed_decisions",
                "reported_controls",
                "publication_status",
                "report_ready",
            }
        ),
        label="case",
    )
    _constant(
        case["schema_version"],
        expected=CASE_SCHEMA_VERSION,
        label="case.schema_version",
    )
    _bootstrap_case_identity(case)
    _constant(case["case_status"], expected="reviewed", label="case.case_status")
    _text(case["reviewer_role"], label="case.reviewer_role")

    source = _mapping(case["source"], label="case.source")
    _exact_fields(
        source,
        required=frozenset({"source_id", "declared_data_kind"}),
        label="case.source",
    )
    _opaque_identifier(
        source["source_id"],
        pattern=SOURCE_ID_PATTERN,
        label="case.source.source_id",
    )
    _constant(
        source["declared_data_kind"],
        expected="commercial_general_ledger",
        label="case.source.declared_data_kind",
    )

    bindings = _mapping(case["bindings"], label="case.bindings")
    binding_fields = frozenset(
        {
            "source_sha256",
            "intake_receipt_sha256",
            "semantic_review_receipt_sha256",
            "semantic_decisions_sha256",
            "parser_layout_sha256",
            "parser_adapter_implementation_sha256",
            "parser_implementation_sha256",
        }
    )
    _exact_fields(bindings, required=binding_fields, label="case.bindings")
    validated_bindings = {
        field: _digest(bindings[field], label=f"case.bindings.{field}")
        for field in sorted(binding_fields)
    }
    _constant(
        validated_bindings["intake_receipt_sha256"],
        expected=intake_receipt_sha256,
        label="case.bindings.intake_receipt_sha256",
    )
    _constant(
        validated_bindings["semantic_review_receipt_sha256"],
        expected=semantic_receipt_sha256,
        label="case.bindings.semantic_review_receipt_sha256",
    )
    _constant(
        validated_bindings["semantic_decisions_sha256"],
        expected=semantic_decisions_sha256,
        label="case.bindings.semantic_decisions_sha256",
    )
    _constant(
        validated_bindings["parser_layout_sha256"],
        expected=file_sha256(parser_layout_path),
        label="case.bindings.parser_layout_sha256",
    )
    _constant(
        validated_bindings["parser_adapter_implementation_sha256"],
        expected=file_sha256(parser_adapter_implementation_path),
        label="case.bindings.parser_adapter_implementation_sha256",
    )
    _constant(
        validated_bindings["parser_implementation_sha256"],
        expected=file_sha256(parser_implementation_path),
        label="case.bindings.parser_implementation_sha256",
    )
    observed_parser_path = inspect.getsourcefile(parser)
    if (
        observed_parser_path is None
        or Path(observed_parser_path).resolve()
        != parser_adapter_implementation_path.resolve()
    ):
        raise ContractValidationError(
            "parser callable does not match parser_adapter_implementation_path"
        )
    if parser is not parse_reviewed_commercial_general_journal:
        raise ContractValidationError(
            "real-data production requires the first-class parser adapter"
        )
    if (
        parser_adapter_implementation_path.resolve() != Path(__file__).resolve()
        or parser_implementation_path.resolve() != GENERAL_JOURNAL_PARSER_PATH
    ):
        raise ContractValidationError(
            "first-class parser adapter must bind its exact implementation files"
        )

    _validate_reviewed_projection(
        reviewed_period_value=case["reviewed_period"],
        reviewed_decisions_value=case["reviewed_decisions"],
        reported_controls_value=case["reported_controls"],
        label="case",
    )
    _constant(
        case["publication_status"],
        expected="withheld",
        label="case.publication_status",
    )
    _constant(case["report_ready"], expected=False, label="case.report_ready")
    return {
        **dict(case),
        "_case_sha256": case_sha256,
        "_bindings": validated_bindings,
    }


def _validate_semantic_decisions(
    value: Any,
    *,
    case: Mapping[str, Any],
) -> dict[str, Any]:
    decisions_artifact = _mapping(value, label="semantic decisions")
    _exact_fields(
        decisions_artifact,
        required=frozenset(
            {
                "schema_version",
                "pilot_id",
                "source_id",
                "review_status",
                "reviewer_role",
                "reviewed_period",
                "reviewed_decisions",
                "reported_controls",
                "publication_status",
                "report_ready",
            }
        ),
        label="semantic decisions",
    )
    _constant(
        decisions_artifact["schema_version"],
        expected=SEMANTIC_DECISIONS_SCHEMA_VERSION,
        label="semantic decisions.schema_version",
    )
    _opaque_identifier(
        decisions_artifact["pilot_id"],
        pattern=PILOT_ID_PATTERN,
        label="semantic decisions.pilot_id",
    )
    _opaque_identifier(
        decisions_artifact["source_id"],
        pattern=SOURCE_ID_PATTERN,
        label="semantic decisions.source_id",
    )
    _constant(
        decisions_artifact["review_status"],
        expected="reviewed",
        label="semantic decisions.review_status",
    )
    _text(
        decisions_artifact["reviewer_role"],
        label="semantic decisions.reviewer_role",
    )
    _validate_reviewed_projection(
        reviewed_period_value=decisions_artifact["reviewed_period"],
        reviewed_decisions_value=decisions_artifact["reviewed_decisions"],
        reported_controls_value=decisions_artifact["reported_controls"],
        label="semantic decisions",
    )
    _constant(
        decisions_artifact["publication_status"],
        expected="withheld",
        label="semantic decisions.publication_status",
    )
    _constant(
        decisions_artifact["report_ready"],
        expected=False,
        label="semantic decisions.report_ready",
    )
    case_source = _mapping(case["source"], label="case.source")
    for field, actual, expected in (
        ("pilot_id", decisions_artifact["pilot_id"], case["pilot_id"]),
        ("source_id", decisions_artifact["source_id"], case_source["source_id"]),
        (
            "reviewer_role",
            decisions_artifact["reviewer_role"],
            case["reviewer_role"],
        ),
        (
            "reviewed_period",
            decisions_artifact["reviewed_period"],
            case["reviewed_period"],
        ),
        (
            "reviewed_decisions",
            decisions_artifact["reviewed_decisions"],
            case["reviewed_decisions"],
        ),
        (
            "reported_controls",
            decisions_artifact["reported_controls"],
            case["reported_controls"],
        ),
    ):
        _constant(
            actual,
            expected=expected,
            label=f"semantic decisions.{field}",
        )
    return dict(decisions_artifact)


def _require_semantic_decisions_evidence(
    semantic_review: Any,
    *,
    semantic_review_path: Path,
    semantic_decisions_path: Path,
    semantic_decisions_byte_count: int,
    semantic_decisions_sha256: str,
) -> None:
    review = _mapping(semantic_review, label="semantic review")
    registry = _mapping(
        review.get("evidence_registry"),
        label="semantic review.evidence_registry",
    )
    matching_records: list[tuple[str, Mapping[str, Any]]] = []
    expected_path = semantic_decisions_path.resolve()
    for evidence_id, raw_record in registry.items():
        evidence_id = _text(
            evidence_id,
            label="semantic review.evidence_registry key",
        )
        record = _mapping(
            raw_record,
            label=f"semantic review.evidence_registry.{evidence_id}",
        )
        raw_path = Path(
            _text(
                record.get("path"),
                label=f"semantic review.evidence_registry.{evidence_id}.path",
            )
        )
        if raw_path.is_absolute():
            continue
        if (semantic_review_path.parent / raw_path).resolve() == expected_path:
            matching_records.append((evidence_id, record))
    if len(matching_records) != 1:
        raise ContractValidationError(
            "semantic review must reference the exact semantic decisions artifact once"
        )
    evidence_id, record = matching_records[0]
    for field, expected in (
        ("media_type", "application/json"),
        ("byte_count", semantic_decisions_byte_count),
        ("sha256", semantic_decisions_sha256),
    ):
        _constant(
            record.get(field),
            expected=expected,
            label=f"semantic decisions evidence.{field}",
        )

    raw_reviews = review.get("required_reviews")
    if not isinstance(raw_reviews, list):
        raise ContractValidationError("semantic review.required_reviews must be a list")
    referenced_topics: set[str] = set()
    for position, raw_review in enumerate(raw_reviews):
        required_review = _mapping(
            raw_review,
            label=f"semantic review.required_reviews[{position}]",
        )
        topic = _text(
            required_review.get("topic"),
            label=f"semantic review.required_reviews[{position}].topic",
        )
        raw_refs = required_review.get("evidence_refs")
        if (
            not isinstance(raw_refs, list)
            or any(not isinstance(ref, str) for ref in raw_refs)
            or evidence_id not in raw_refs
        ):
            raise ContractValidationError(
                "every required semantic review must reference the exact "
                "semantic decisions artifact"
            )
        referenced_topics.add(topic)
    if referenced_topics != set(REQUIRED_SEMANTIC_REVIEWS):
        raise ContractValidationError(
            "semantic decisions evidence must close every required review topic"
        )


def _replay_gate(
    *,
    case: Mapping[str, Any],
    intake_receipt: Mapping[str, Any],
    intake_receipt_sha256: str,
    semantic_receipt: Mapping[str, Any],
    semantic_receipt_sha256: str,
) -> None:
    if intake_receipt.get("schema_version") != INTAKE_RECEIPT_SCHEMA_V2:
        raise _ProducerFailure("contract", "intake_receipt_invalid")
    try:
        validated_intake = validate_real_data_pilot_intake_receipt_v2(intake_receipt)
    except (ContractValidationError, OSError, TypeError, ValueError) as exc:
        raise _ProducerFailure("contract", "intake_receipt_invalid") from exc
    if semantic_receipt.get("schema_version") != SEMANTIC_REVIEW_RECEIPT_SCHEMA:
        raise _ProducerFailure("contract", "semantic_receipt_invalid")
    try:
        validated_semantic = validate_real_data_pilot_semantic_review_receipt(
            semantic_receipt
        )
    except (ContractValidationError, OSError, TypeError, ValueError) as exc:
        raise _ProducerFailure("contract", "semantic_receipt_invalid") from exc

    pilot_id = case["pilot_id"]
    source = _mapping(case["source"], label="case.source")
    bindings = _mapping(case["_bindings"], label="case._bindings")
    intake_source = _mapping(
        validated_intake["source_receipt"],
        label="intake receipt.source_receipt",
    )
    for actual, expected in (
        (validated_intake["pilot_id"], pilot_id),
        (validated_semantic["pilot_id"], pilot_id),
        (intake_source["source_id"], source["source_id"]),
        (intake_source["declared_data_kind"], "commercial_general_ledger"),
        (intake_source["sha256"], bindings["source_sha256"]),
        (
            validated_semantic["intake_receipt_sha256"],
            intake_receipt_sha256,
        ),
        (bindings["semantic_review_receipt_sha256"], semantic_receipt_sha256),
    ):
        if actual != expected:
            raise _ProducerFailure("contract", "case_or_binding_invalid")


def _validate_movements(
    raw_movements: Sequence[Movement],
    *,
    reviewed_year: int,
) -> list[Movement]:
    if not raw_movements:
        raise _ProducerFailure("parser", "empty_movement_set")
    movements: list[Movement] = []
    movement_ids: set[str] = set()
    previous_movement_id: int | None = None
    previous_posting_date: date | None = None
    for movement in raw_movements:
        if not isinstance(movement, Movement):
            raise _ProducerFailure("parser", "parser_mechanical_failure")
        movement_id = movement.movement_id
        if (
            not isinstance(movement_id, str)
            or not movement_id
            or movement_id != movement_id.strip()
            or re.fullmatch(r"[1-9][0-9]*", movement_id) is None
        ):
            raise _ProducerFailure(
                "movement_identity",
                "invalid_movement_sequence",
            )
        if movement_id in movement_ids:
            raise _ProducerFailure(
                "movement_identity",
                "duplicate_movement_id",
            )
        movement_ids.add(movement_id)
        numeric_movement_id = int(movement_id)
        if (
            previous_movement_id is not None
            and numeric_movement_id <= previous_movement_id
        ):
            raise _ProducerFailure(
                "movement_identity",
                "invalid_movement_sequence",
            )
        previous_movement_id = numeric_movement_id
        account_code = movement.source_account_code
        if (
            not isinstance(account_code, str)
            or not account_code
            or account_code != account_code.strip()
            or len(account_code) > 256
            or account_code[0] in "=+-@"
            or any(character in account_code for character in ("\r", "\n", "\0"))
            or any(character.isspace() for character in account_code)
        ):
            raise _ProducerFailure(
                "movement_identity",
                "invalid_source_account_identity",
            )
        if type(movement.posting_date) is not date:
            raise _ProducerFailure(
                "period",
                "posting_date_outside_reviewed_year",
            )
        if movement.posting_date.year != reviewed_year:
            raise _ProducerFailure(
                "period",
                "posting_date_outside_reviewed_year",
            )
        if (
            previous_posting_date is not None
            and movement.posting_date < previous_posting_date
        ):
            raise _ProducerFailure(
                "period",
                "posting_date_outside_reviewed_year",
            )
        previous_posting_date = movement.posting_date
        if (
            not isinstance(movement.debit, Decimal)
            or not isinstance(movement.credit, Decimal)
            or not movement.debit.is_finite()
            or not movement.credit.is_finite()
            or movement.debit < 0
            or movement.credit < 0
            or (movement.debit > 0 and movement.credit > 0)
        ):
            raise _ProducerFailure(
                "numeric",
                "invalid_decimal_or_source_sign",
            )
        movements.append(movement)
    return movements


def _work_precision(values: Sequence[Decimal]) -> int:
    if not values:
        return 3
    common_scale = 0
    maximum_integer_digits = 1
    for value in values:
        parts = value.as_tuple()
        if not isinstance(parts.exponent, int):
            raise _ProducerFailure("numeric", "invalid_decimal_or_source_sign")
        common_scale = max(common_scale, max(-parts.exponent, 0))
        maximum_integer_digits = max(
            maximum_integer_digits,
            max(len(parts.digits) + parts.exponent, 0),
        )
    carry_digits = len(str(len(values) + 1))
    return maximum_integer_digits + common_scale + carry_digits + 2


def _aggregate(
    movements: Sequence[Movement],
) -> tuple[
    list[tuple[tuple[str, str], Decimal, Decimal, Decimal]],
    Decimal,
    Decimal,
]:
    values = [
        amount for movement in movements for amount in (movement.debit, movement.credit)
    ]
    aggregates: dict[tuple[str, str], list[Decimal]] = {}
    with localcontext() as context:
        context.prec = _work_precision(values)
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        total_debit = Decimal(0)
        total_credit = Decimal(0)
        for movement in movements:
            period = (
                f"{movement.posting_date.year:04d}-"
                f"{movement.posting_date.month:02d}"
            )
            key = (
                movement.source_account_code,
                period,
            )
            amounts = aggregates.setdefault(key, [Decimal(0), Decimal(0)])
            amounts[0] += movement.debit
            amounts[1] += movement.credit
            total_debit += movement.debit
            total_credit += movement.credit
        rows = [
            (
                key,
                amounts[0],
                -amounts[1],
                amounts[0] - amounts[1],
            )
            for key, amounts in sorted(aggregates.items())
        ]
    return rows, total_debit, total_credit


def _account_month_csv(
    rows: Sequence[tuple[tuple[str, str], Decimal, Decimal, Decimal]],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "source_account_code",
            "calendar_month",
            "debit_positive",
            "credit_negative",
            "net_movement",
        )
    )
    for (code, period), debit, credit, net in rows:
        writer.writerow(
            (
                code,
                period,
                decimal_text(debit),
                decimal_text(credit),
                decimal_text(net),
            )
        )
    return stream.getvalue().encode("utf-8")


def _balanced_month_count(
    rows: Sequence[tuple[tuple[str, str], Decimal, Decimal, Decimal]],
) -> tuple[int, int]:
    values = [
        amount for _key, debit, credit, _net in rows for amount in (debit, credit)
    ]
    months: dict[str, list[Decimal]] = {}
    with localcontext() as context:
        context.prec = _work_precision(values)
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        for (_account_code, month), debit, credit, _net in rows:
            month_totals = months.setdefault(month, [Decimal(0), Decimal(0)])
            month_totals[0] += debit
            month_totals[1] += -credit
    balanced = sum(1 for debit, credit in months.values() if debit == credit)
    return balanced, len(months)


def _mechanical_bindings(
    *,
    case_sha256: str,
    intake_receipt_sha256: str,
    semantic_receipt_sha256: str,
    closure_sha256: str,
) -> dict[str, str]:
    bindings = {
        "case_contract_sha256": case_sha256,
        "intake_receipt_sha256": intake_receipt_sha256,
        "output_receipt_closure_sha256": closure_sha256,
        "producer_contract_sha256": producer_contract_sha256(),
        "producer_implementation_sha256": file_sha256(Path(__file__).resolve()),
        "semantic_review_receipt_sha256": semantic_receipt_sha256,
    }
    if set(bindings) != set(BINDING_FIELDS):
        raise ContractValidationError("producer bindings are not registered")
    return bindings


def producer_contract_sha256() -> str:
    """Bind the exact case and semantic-decision schemas as one contract."""

    digest = hashlib.sha256()
    digest.update(b"clara.real-general-ledger-producer-contracts.v1\0")
    for path in sorted(
        (CASE_SCHEMA_PATH, SEMANTIC_DECISIONS_SCHEMA_PATH),
        key=lambda item: item.name,
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _mechanical_register(
    *,
    pilot_id: str,
    execution_id: str,
    bindings: Mapping[str, str],
    failure: _ProducerFailure | None,
) -> dict[str, Any]:
    failure_position = (
        None
        if failure is None
        else next(
            position
            for position, spec in enumerate(CHECK_SPECS)
            if spec.key == failure.check_key
        )
    )
    checks: dict[str, Any] = {}
    for position, spec in enumerate(CHECK_SPECS):
        if failure_position is None or position < failure_position:
            status = "passed"
        elif position == failure_position:
            status = "failed"
        else:
            status = "not_run"
        checks[CHECK_IDS[spec.key]] = {
            "mechanical_class": spec.mechanical_class,
            "error_codes": sorted(ERROR_CODES[key] for key in spec.error_keys),
            "status": status,
            "artifact_refs": [MECHANICAL_ROLE],
        }
    errors: dict[str, Any] = {}
    if failure is not None:
        spec = next(item for item in CHECK_SPECS if item.key == failure.check_key)
        error_id = _opaque_id("error", failure.error_key)
        errors[error_id] = {
            "check_id": CHECK_IDS[failure.check_key],
            "error_code": ERROR_CODES[failure.error_key],
            "mechanical_class": spec.mechanical_class,
            "artifact_refs": [MECHANICAL_ROLE],
        }
    status_counts = {
        status: sum(1 for check in checks.values() if check["status"] == status)
        for status in ("passed", "failed", "not_run")
    }
    class_counts = {
        mechanical_class: sum(
            1
            for error in errors.values()
            if error["mechanical_class"] == mechanical_class
        )
        for mechanical_class in MECHANICAL_CLASSES
    }
    return {
        "schema_version": MECHANICAL_REGISTER_SCHEMA,
        "pilot_id": pilot_id,
        "execution_id": execution_id,
        "bindings": dict(bindings),
        "check_registry": checks,
        "error_registry": errors,
        "summary": {
            "overall_status": "passed" if failure is None else "failed",
            "check_counts": status_counts,
            "error_count": len(errors),
            "class_counts": class_counts,
        },
        "content_policy": {
            "error_messages_in_register": False,
            "row_level_values_in_register": False,
            "semantic_findings_in_register": False,
        },
        "publication_status": "withheld",
        "report_ready": False,
        "limitations": list(MECHANICAL_LIMITATIONS),
    }


def _close_output(
    *,
    output_directory: Path,
    expected_roles: Mapping[str, str],
    pilot_id: str,
    execution_id: str,
    failure: _ProducerFailure | None,
    case_sha256: str,
    intake_receipt_sha256: str,
    semantic_receipt_sha256: str,
    local_run_root: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    register_path = output_directory / "mechanical_errors.json"
    provisional_bindings = _mechanical_bindings(
        case_sha256=case_sha256,
        intake_receipt_sha256=intake_receipt_sha256,
        semantic_receipt_sha256=semantic_receipt_sha256,
        closure_sha256="0" * 64,
    )
    register = _mechanical_register(
        pilot_id=pilot_id,
        execution_id=execution_id,
        bindings=provisional_bindings,
        failure=failure,
    )
    write_json(register_path, register)
    provisional_receipts = seal_pilot_output_directory(
        output_directory,
        expected_roles=expected_roles,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    closure_sha256 = output_receipt_closure_sha256(provisional_receipts)
    final_bindings = _mechanical_bindings(
        case_sha256=case_sha256,
        intake_receipt_sha256=intake_receipt_sha256,
        semantic_receipt_sha256=semantic_receipt_sha256,
        closure_sha256=closure_sha256,
    )
    register = _mechanical_register(
        pilot_id=pilot_id,
        execution_id=execution_id,
        bindings=final_bindings,
        failure=failure,
    )
    write_json(register_path, register)
    final_receipts = seal_pilot_output_directory(
        output_directory,
        expected_roles=expected_roles,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    validated_register = validate_real_data_pilot_mechanical_error_register(
        register_path,
        expected_pilot_id=pilot_id,
        expected_execution_id=execution_id,
        expected_bindings=final_bindings,
        output_receipts=final_receipts,
        output_directory=output_directory,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    return validated_register, final_receipts


def _input_paths(
    *,
    local_run_root: Path,
    paths: Sequence[Path],
) -> list[Path]:
    root = local_run_root.resolve()
    unique = {path.resolve() for path in paths if path.resolve().is_relative_to(root)}
    return sorted(unique, key=lambda path: path.as_posix())


def run_real_general_ledger_pilot(
    *,
    case_path: Path,
    intake_contract_path: Path,
    intake_receipt_path: Path,
    semantic_review_path: Path,
    semantic_receipt_path: Path,
    semantic_decisions_path: Path,
    source_path: Path,
    parser_layout_path: Path,
    parser_adapter_implementation_path: Path,
    parser_implementation_path: Path,
    output_directory: Path,
    local_run_root: Path,
    repository_root: Path,
    as_of_date: str,
    parser: MovementParser,
) -> PilotRunResult:
    """Run one private pilot and return only a sanitized pass/fail receipt.

    Receipt validation and the reviewer-declared semantic gate always complete
    before :func:`file_snapshot_beneath` hashes the source or ``parser`` is
    called. Expected mechanical failures produce only the fixed, prose-free
    register and never an account-month artifact.
    """

    run_root = local_run_root.resolve()
    case, _, case_sha256 = strict_json_snapshot_beneath(case_path, root=run_root)
    pilot_id, execution_id = _bootstrap_case_identity(case)
    intake_receipt, _, intake_receipt_sha256 = strict_json_snapshot_beneath(
        intake_receipt_path,
        root=run_root,
    )
    semantic_receipt, _, semantic_receipt_sha256 = strict_json_snapshot_beneath(
        semantic_receipt_path,
        root=run_root,
    )
    semantic_review, _, _semantic_review_sha256 = strict_json_snapshot_beneath(
        semantic_review_path,
        root=run_root,
    )
    (
        semantic_decisions,
        semantic_decisions_byte_count,
        semantic_decisions_sha256,
    ) = strict_json_snapshot_beneath(
        semantic_decisions_path,
        root=run_root,
    )
    output_path = create_fresh_pilot_output_directory(
        output_directory,
        local_run_root=run_root,
        repository_root=repository_root,
        input_paths=_input_paths(
            local_run_root=run_root,
            paths=(
                case_path,
                intake_contract_path,
                intake_receipt_path,
                semantic_review_path,
                semantic_receipt_path,
                semantic_decisions_path,
                source_path,
                parser_layout_path,
                parser_adapter_implementation_path,
                parser_implementation_path,
            ),
        ),
    )

    failure: _ProducerFailure | None = None
    validated_case: dict[str, Any] | None = None
    try:
        try:
            validated_case = _validate_case(
                case,
                case_sha256=case_sha256,
                intake_receipt_sha256=intake_receipt_sha256,
                semantic_receipt_sha256=semantic_receipt_sha256,
                semantic_decisions_sha256=semantic_decisions_sha256,
                parser_layout_path=parser_layout_path,
                parser_adapter_implementation_path=parser_adapter_implementation_path,
                parser_implementation_path=parser_implementation_path,
                parser=parser,
            )
        except (ContractValidationError, OSError, TypeError, ValueError) as exc:
            raise _ProducerFailure("contract", "case_or_binding_invalid") from exc
        try:
            _validate_semantic_decisions(
                semantic_decisions,
                case=validated_case,
            )
            _require_semantic_decisions_evidence(
                semantic_review,
                semantic_review_path=semantic_review_path,
                semantic_decisions_path=semantic_decisions_path,
                semantic_decisions_byte_count=semantic_decisions_byte_count,
                semantic_decisions_sha256=semantic_decisions_sha256,
            )
        except (ContractValidationError, OSError, TypeError, ValueError) as exc:
            raise _ProducerFailure("contract", "case_or_binding_invalid") from exc
        _replay_gate(
            case=validated_case,
            intake_receipt=intake_receipt,
            intake_receipt_sha256=intake_receipt_sha256,
            semantic_receipt=semantic_receipt,
            semantic_receipt_sha256=semantic_receipt_sha256,
        )
        try:
            regenerated_semantic = validate_real_data_pilot_semantic_review(
                semantic_review_path,
                intake_receipt_path,
                as_of_date=as_of_date,
                local_run_root=run_root,
                repository_root=repository_root,
            )
        except (ContractValidationError, OSError, TypeError, ValueError) as exc:
            raise _ProducerFailure("contract", "semantic_receipt_invalid") from exc
        if regenerated_semantic != dict(semantic_receipt):
            raise _ProducerFailure("contract", "semantic_receipt_invalid")
        if (
            _mapping(
                regenerated_semantic["readiness"],
                label="semantic receipt.readiness",
            )["mechanical_preparation_allowed"]
            is not True
        ):
            raise _ProducerFailure("contract", "semantic_review_blocked")
        try:
            regenerated_intake = validate_real_data_pilot_intake_v2(
                intake_contract_path,
                source_path,
                as_of_date=as_of_date,
                local_run_root=run_root,
                repository_root=repository_root,
            )
        except (ContractValidationError, OSError, TypeError, ValueError) as exc:
            raise _ProducerFailure("source", "source_receipt_mismatch") from exc
        if regenerated_intake != dict(intake_receipt):
            raise _ProducerFailure("source", "source_receipt_mismatch")
        try:
            source_sha256 = _mapping(
                validated_case["_bindings"],
                label="case._bindings",
            )["source_sha256"]
            parsed_batch = parser(
                source_path,
                expected_source_sha256=source_sha256,
                parser_layout_path=parser_layout_path,
                expected_parser_layout_sha256=_mapping(
                    validated_case["_bindings"],
                    label="case._bindings",
                )["parser_layout_sha256"],
            )
            if not isinstance(parsed_batch, ParsedMovementBatch):
                raise ParserMechanicalError
        except (
            ContractValidationError,
            OSError,
            ParserMechanicalError,
            TypeError,
            ValueError,
        ) as exc:
            raise _ProducerFailure("parser", "parser_mechanical_failure") from exc
        try:
            _source_byte_count, current_source_sha256 = file_snapshot_beneath(
                source_path,
                root=run_root,
            )
        except (ContractValidationError, OSError) as exc:
            raise _ProducerFailure("source", "source_receipt_mismatch") from exc
        case_bindings = _mapping(
            validated_case["_bindings"],
            label="case._bindings",
        )
        if current_source_sha256 != case_bindings["source_sha256"]:
            raise _ProducerFailure("source", "source_receipt_mismatch")
        if parsed_batch.source_sha256 != case_bindings["source_sha256"]:
            raise _ProducerFailure("source", "source_receipt_mismatch")
        try:
            current_parser_hashes = {
                "parser_layout_sha256": file_sha256(parser_layout_path),
                "parser_adapter_implementation_sha256": file_sha256(
                    parser_adapter_implementation_path
                ),
                "parser_implementation_sha256": file_sha256(parser_implementation_path),
            }
        except OSError as exc:
            raise _ProducerFailure("contract", "case_or_binding_invalid") from exc
        if any(
            case_bindings[field] != digest
            for field, digest in current_parser_hashes.items()
        ):
            raise _ProducerFailure("contract", "case_or_binding_invalid")
        reviewed_year = _mapping(
            validated_case["reviewed_period"],
            label="case.reviewed_period",
        )["year"]
        movements = _validate_movements(
            parsed_batch.movements,
            reviewed_year=reviewed_year,
        )
        try:
            rows, total_debit, total_credit = _aggregate(movements)
        except (ArithmeticError, ContractValidationError) as exc:
            raise _ProducerFailure(
                "numeric",
                "invalid_decimal_or_source_sign",
            ) from exc
        controls = _mapping(
            validated_case["reported_controls"],
            label="case.reported_controls",
        )
        reported_debit = parse_decimal(
            controls["debit"],
            label="case.reported_controls.debit",
            non_negative=True,
            canonical=True,
        )
        reported_credit = parse_decimal(
            controls["credit"],
            label="case.reported_controls.credit",
            non_negative=True,
            canonical=True,
        )
        source_control_debit = parsed_batch.source_control_debit
        source_control_credit = parsed_batch.source_control_credit
        if (
            not isinstance(source_control_debit, Decimal)
            or not isinstance(source_control_credit, Decimal)
            or not source_control_debit.is_finite()
            or not source_control_credit.is_finite()
            or source_control_debit < 0
            or source_control_credit < 0
            or source_control_debit != source_control_credit
        ):
            raise _ProducerFailure(
                "reconciliation",
                "source_control_mismatch",
            )
        if source_control_debit != total_debit or source_control_credit != total_credit:
            raise _ProducerFailure(
                "reconciliation",
                "source_control_mismatch",
            )
        if (
            source_control_debit != reported_debit
            or source_control_credit != reported_credit
        ):
            raise _ProducerFailure(
                "reconciliation",
                "reported_control_mismatch",
            )
        balanced_month_count, emitted_month_count = _balanced_month_count(rows)
        if balanced_month_count != emitted_month_count:
            raise _ProducerFailure(
                "reconciliation",
                "monthly_balance_mismatch",
            )
        expected_calendar_months = controls["expected_calendar_months"]
        emitted_calendar_months = sorted({key[1] for key, *_amounts in rows})
        if emitted_calendar_months != expected_calendar_months:
            raise _ProducerFailure(
                "month_coverage",
                "calendar_month_coverage_mismatch",
            )
    except _ProducerFailure as exc:
        failure = exc

    if failure is not None:
        _register, receipts = _close_output(
            output_directory=output_path,
            expected_roles=FAILURE_ROLES,
            pilot_id=pilot_id,
            execution_id=execution_id,
            failure=failure,
            case_sha256=case_sha256,
            intake_receipt_sha256=intake_receipt_sha256,
            semantic_receipt_sha256=semantic_receipt_sha256,
            local_run_root=run_root,
            repository_root=repository_root,
        )
        return PilotRunResult(
            status="failed",
            output_directory=output_path,
            output_receipts=tuple(receipts),
            failure_code=ERROR_CODES[failure.error_key],
        )

    if validated_case is None:
        raise ContractValidationError("validated case is unavailable")
    artifacts_path = output_path / "artifacts"
    artifacts_path.mkdir(mode=0o700)
    (artifacts_path / f"{ACCOUNT_MONTH_ROLE}.bin").write_bytes(_account_month_csv(rows))
    case_bindings = _mapping(validated_case["_bindings"], label="case._bindings")
    reconciliation = {
        "schema_version": "clara.real_general_ledger_reconciliation.v1",
        "pilot_id": pilot_id,
        "execution_id": execution_id,
        "bindings": {
            "case_contract_sha256": case_sha256,
            "intake_receipt_sha256": intake_receipt_sha256,
            "parser_implementation_sha256": case_bindings[
                "parser_implementation_sha256"
            ],
            "parser_adapter_implementation_sha256": case_bindings[
                "parser_adapter_implementation_sha256"
            ],
            "parser_layout_sha256": case_bindings["parser_layout_sha256"],
            "producer_contract_sha256": producer_contract_sha256(),
            "producer_implementation_sha256": file_sha256(Path(__file__).resolve()),
            "semantic_decisions_sha256": semantic_decisions_sha256,
            "semantic_review_receipt_sha256": semantic_receipt_sha256,
            "source_sha256": case_bindings["source_sha256"],
        },
        "counts": {
            "source_movement_count": len(movements),
            "account_month_count": len(rows),
        },
        "controls": {
            "basis": "exact_extracted_final_debit_and_credit_controls",
            "reported_debit": decimal_text(reported_debit),
            "source_control_debit": decimal_text(source_control_debit),
            "calculated_debit": decimal_text(total_debit),
            "debit_difference": decimal_text(total_debit - reported_debit),
            "reported_credit": decimal_text(reported_credit),
            "source_control_credit": decimal_text(source_control_credit),
            "calculated_credit": decimal_text(total_credit),
            "credit_difference": decimal_text(total_credit - reported_credit),
            "tolerance": "0",
            "status": "passed",
            "journal_balance_required": True,
            "monthly_balance_required": True,
            "balanced_month_count": balanced_month_count,
            "emitted_month_count": emitted_month_count,
            "expected_month_count": len(expected_calendar_months),
            "expected_calendar_months": expected_calendar_months,
            "emitted_calendar_months": emitted_calendar_months,
            "monthly_balance_status": "passed",
        },
        "sign_convention": "debit_positive_credit_negative",
        "output_grain": "source_account_x_calendar_month",
        "publication_status": "withheld",
        "report_ready": False,
    }
    write_json(
        artifacts_path / f"{RECONCILIATION_ROLE}.bin",
        reconciliation,
    )
    _register, receipts = _close_output(
        output_directory=output_path,
        expected_roles=SUCCESS_ROLES,
        pilot_id=pilot_id,
        execution_id=execution_id,
        failure=None,
        case_sha256=case_sha256,
        intake_receipt_sha256=intake_receipt_sha256,
        semantic_receipt_sha256=semantic_receipt_sha256,
        local_run_root=run_root,
        repository_root=repository_root,
    )
    return PilotRunResult(
        status="passed",
        output_directory=output_path,
        output_receipts=tuple(receipts),
        failure_code=None,
    )
