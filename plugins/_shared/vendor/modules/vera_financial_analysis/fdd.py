"""Reviewed-input machinery for bounded financial due diligence.

The calculations in this module are deterministic because exact arithmetic,
reference closure, duplicate detection, and canonical output hashes are
mechanically verifiable. Accounting classifications, adjustment inclusion,
working-capital targets, Capex purpose, contingency treatment, and deal
decisions remain reviewed inputs and are never inferred here.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from vera_assurance.money import decimal_text, parse_canonical_decimal
from vera_assurance.serialization import canonical_json_sha256

from .contracts import (
    build_analysis_pack_request,
    validate_analysis_pack_request,
    validate_crosswalk_manifest,
    validate_data_package_manifest,
    validate_dataset_contract,
    validate_relationship_contract,
)
from .registry import (
    FDD_ENGINE_VERSION,
    FDD_OUTPUT_ROLES,
    FDD_PACK_RECIPES,
)

__all__ = [
    "FDD_ENGINE_VERSION",
    "FDD_OUTPUT_ROLES",
    "FDD_PACK_RECIPES",
    "FDDContractError",
    "build_fdd_metric_receipt",
    "build_contingent_liability_register",
    "build_fdd_case",
    "build_financial_issue_register",
    "execute_fdd_case",
    "validate_contingent_liability_register",
    "validate_fdd_calculation_result",
    "validate_fdd_case",
    "validate_fdd_metric_receipt",
    "validate_financial_issue_register",
]

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CASH_EFFECTS = {"cash", "mixed", "non_cash", "not_assessed"}
_NET_DEBT_CLASSIFICATIONS = {
    "cash",
    "cash_like",
    "debt",
    "debt_like",
    "excluded",
}
_CAPEX_BASES = {
    "asset_addition",
    "capitalized_amount",
    "cash_paid",
    "disposal_proceeds",
}
_CAPEX_CLASSIFICATIONS = {
    "excluded",
    "growth",
    "maintenance",
    "mixed",
    "unclassified",
}
_AMOUNT_STATUSES = {"exact", "range", "unquantified"}


class FDDContractError(ValueError):
    """Raised when an FDD case, register, or calculation is inconsistent."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FDDContractError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FDDContractError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FDDContractError(f"{label} must be non-empty trimmed text")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_PATTERN.fullmatch(text) is None:
        raise FDDContractError(f"{label} must be a canonical identifier")
    return text


def _identifier_list(
    value: object,
    *,
    label: str,
    allow_empty: bool = False,
) -> list[str]:
    items = [
        _identifier(item, label=f"{label}[{index}]")
        for index, item in enumerate(_sequence(value, label=label))
    ]
    if (not items and not allow_empty) or len(items) != len(set(items)):
        requirement = "unique" if allow_empty else "non-empty and unique"
        raise FDDContractError(f"{label} must be {requirement}")
    return items


def _text_list(
    value: object,
    *,
    label: str,
    allow_empty: bool = True,
) -> list[str]:
    items = [
        _text(item, label=f"{label}[{index}]")
        for index, item in enumerate(_sequence(value, label=label))
    ]
    if not allow_empty and not items:
        raise FDDContractError(f"{label} must not be empty")
    return items


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: set[str],
    label: str,
) -> None:
    missing = required - set(value)
    unexpected = set(value) - required
    if missing or unexpected:
        raise FDDContractError(
            f"{label} fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _iso_date(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise FDDContractError(f"{label} must be an ISO date") from exc
    if parsed.isoformat() != text:
        raise FDDContractError(f"{label} must use YYYY-MM-DD")
    return text


def _decimal(value: object, *, label: str) -> Decimal:
    try:
        return parse_canonical_decimal(value, label=label)
    except ValueError as exc:
        raise FDDContractError(str(exc)) from exc


def _non_negative_decimal(value: object, *, label: str) -> Decimal:
    amount = _decimal(value, label=label)
    if amount < 0:
        raise FDDContractError(f"{label} must be non-negative")
    return amount


def _decimal_components(value: Decimal) -> tuple[int, int]:
    parts = value.as_tuple()
    coefficient = int("".join(str(digit) for digit in parts.digits) or "0")
    if parts.sign:
        coefficient = -coefficient
    if not isinstance(parts.exponent, int):
        raise FDDContractError("monetary values must be finite")
    return coefficient, parts.exponent


def _decimal_from_components(coefficient: int, exponent: int) -> Decimal:
    sign = 1 if coefficient < 0 else 0
    digits = tuple(int(character) for character in str(abs(coefficient)))
    return Decimal((sign, digits, exponent))


def _exact_sum(values: Sequence[Decimal]) -> Decimal:
    """Add finite Decimals without depending on the ambient Decimal context."""

    if not values:
        return Decimal(0)
    components = [_decimal_components(value) for value in values]
    common_exponent = min(exponent for _, exponent in components)
    coefficient = sum(
        value * (10 ** (exponent - common_exponent)) for value, exponent in components
    )
    return _decimal_from_components(coefficient, common_exponent)


def _exact_product(left: Decimal, right: Decimal) -> Decimal:
    """Multiply finite Decimals without depending on ambient precision."""

    left_coefficient, left_exponent = _decimal_components(left)
    right_coefficient, right_exponent = _decimal_components(right)
    return _decimal_from_components(
        left_coefficient * right_coefficient,
        left_exponent + right_exponent,
    )


def _exact_negate(value: Decimal) -> Decimal:
    """Negate a Decimal without applying the ambient precision."""

    return value.copy_negate()


def _non_negative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise FDDContractError(f"{label} must be a non-negative integer")
    return value


def _boolean(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise FDDContractError(f"{label} must be boolean")
    return value


def _sha256(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise FDDContractError(f"{label} must be lowercase SHA-256 text")
    return text


def _seal(content: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    return {**normalized, "content_sha256": canonical_json_sha256(normalized)}


def _sealed_content(
    value: object,
    *,
    schema_version: str,
    required: set[str],
    label: str,
) -> dict[str, Any]:
    payload = _mapping(value, label=label)
    _exact_fields(
        payload,
        required={"schema_version", *required, "content_sha256"},
        label=label,
    )
    if payload["schema_version"] != schema_version:
        raise FDDContractError(f"unsupported {label} schema")
    content = {key: payload[key] for key in payload if key != "content_sha256"}
    if payload["content_sha256"] != canonical_json_sha256(content):
        raise FDDContractError(f"{label} content digest is stale")
    return content


def _normalize_review(value: object, *, label: str = "review") -> dict[str, str]:
    review = _mapping(value, label=label)
    _exact_fields(
        review,
        required={"status", "reviewed_on", "reviewer_ref", "basis"},
        label=label,
    )
    if review["status"] != "reviewed":
        raise FDDContractError(f"{label}.status must be reviewed")
    return {
        "status": "reviewed",
        "reviewed_on": _iso_date(review["reviewed_on"], label=f"{label}.reviewed_on"),
        "reviewer_ref": _identifier(
            review["reviewer_ref"], label=f"{label}.reviewer_ref"
        ),
        "basis": _text(review["basis"], label=f"{label}.basis"),
    }


def _normalize_source_artifacts(value: object) -> list[dict[str, Any]]:
    artifacts = []
    for index, raw_artifact in enumerate(_sequence(value, label="source_artifacts")):
        label = f"source_artifacts[{index}]"
        artifact = _mapping(raw_artifact, label=label)
        _exact_fields(
            artifact,
            required={
                "artifact_ref",
                "byte_count",
                "dataset_contract_ref",
                "role",
                "sha256",
            },
            label=label,
        )
        artifacts.append(
            {
                "artifact_ref": _identifier(
                    artifact["artifact_ref"], label=f"{label}.artifact_ref"
                ),
                "dataset_contract_ref": _identifier(
                    artifact["dataset_contract_ref"],
                    label=f"{label}.dataset_contract_ref",
                ),
                "role": _identifier(artifact["role"], label=f"{label}.role"),
                "byte_count": _non_negative_int(
                    artifact["byte_count"], label=f"{label}.byte_count"
                ),
                "sha256": _sha256(artifact["sha256"], label=f"{label}.sha256"),
            }
        )
    artifacts.sort(key=lambda item: item["artifact_ref"])
    refs = [item["artifact_ref"] for item in artifacts]
    if not artifacts or len(refs) != len(set(refs)):
        raise FDDContractError(
            "source_artifacts must be non-empty with unique artifact_ref values"
        )
    return artifacts


def _normalize_reviewed_decisions(value: object) -> list[dict[str, str]]:
    decisions = []
    for index, raw_decision in enumerate(_sequence(value, label="reviewed_decisions")):
        label = f"reviewed_decisions[{index}]"
        decision = _mapping(raw_decision, label=label)
        _exact_fields(
            decision,
            required={
                "basis",
                "decision_ref",
                "reviewed_on",
                "reviewer_ref",
                "status",
            },
            label=label,
        )
        review = _normalize_review(
            {
                "status": decision["status"],
                "reviewed_on": decision["reviewed_on"],
                "reviewer_ref": decision["reviewer_ref"],
                "basis": decision["basis"],
            },
            label=label,
        )
        decisions.append(
            {
                "decision_ref": _identifier(
                    decision["decision_ref"], label=f"{label}.decision_ref"
                ),
                **review,
            }
        )
    decisions.sort(key=lambda item: item["decision_ref"])
    _unique_rows(decisions, "decision_ref", label="reviewed_decisions")
    if not decisions:
        raise FDDContractError("reviewed_decisions must not be empty")
    return decisions


def _closed_decision_ref(
    value: object,
    *,
    label: str,
    available_refs: set[str],
) -> str:
    decision_ref = _identifier(value, label=label)
    if decision_ref not in available_refs:
        raise FDDContractError(f"{label} is not a reviewed decision")
    return decision_ref


def _normalize_evidence_refs(
    value: object,
    *,
    label: str,
    available_refs: set[str],
) -> list[str]:
    refs = sorted(_identifier_list(value, label=label))
    missing = sorted(set(refs) - available_refs)
    if missing:
        raise FDDContractError(f"{label} has unknown artifact references: {missing}")
    return refs


def _normalize_evidenced_amount(
    value: object,
    *,
    label: str,
    available_refs: set[str],
    non_negative: bool = False,
    decision_refs: set[str] | None = None,
) -> dict[str, Any]:
    amount = _mapping(value, label=label)
    required = {"amount", "evidence_refs"}
    if decision_refs is not None:
        required.add("decision_ref")
    _exact_fields(amount, required=required, label=label)
    parser = _non_negative_decimal if non_negative else _decimal
    normalized = {
        "amount": decimal_text(parser(amount["amount"], label=f"{label}.amount")),
        "evidence_refs": _normalize_evidence_refs(
            amount["evidence_refs"],
            label=f"{label}.evidence_refs",
            available_refs=available_refs,
        ),
    }
    if decision_refs is not None:
        normalized["decision_ref"] = _closed_decision_ref(
            amount["decision_ref"],
            label=f"{label}.decision_ref",
            available_refs=decision_refs,
        )
    return normalized


def _normalize_period(value: object) -> dict[str, str]:
    period = _mapping(value, label="reporting_period")
    _exact_fields(
        period,
        required={"start", "end"},
        label="reporting_period",
    )
    start = _iso_date(period["start"], label="reporting_period.start")
    end = _iso_date(period["end"], label="reporting_period.end")
    if end < start:
        raise FDDContractError("reporting_period.end precedes start")
    return {"start": start, "end": end}


def _unique_rows(rows: Sequence[Mapping[str, Any]], key: str, *, label: str) -> None:
    values = [str(row[key]) for row in rows]
    if len(values) != len(set(values)):
        raise FDDContractError(f"{label} must have unique {key} values")


def _normalize_quality_of_earnings(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> dict[str, Any]:
    inputs = _mapping(value, label="inputs")
    _exact_fields(
        inputs,
        required={"reported_ebitda", "adjustments"},
        label="inputs",
    )
    adjustments = []
    for index, raw_row in enumerate(
        _sequence(inputs["adjustments"], label="adjustments")
    ):
        label = f"adjustments[{index}]"
        row = _mapping(raw_row, label=label)
        _exact_fields(
            row,
            required={
                "adjustment_id",
                "category_id",
                "cash_effect",
                "description",
                "decision_ref",
                "ebitda_impact",
                "economic_effect_id",
                "evidence_refs",
                "included",
                "period_end",
                "period_start",
            },
            label=label,
        )
        cash_effect = _identifier(row["cash_effect"], label=f"{label}.cash_effect")
        if cash_effect not in _CASH_EFFECTS:
            raise FDDContractError(f"{label}.cash_effect is unsupported")
        period_start = _iso_date(row["period_start"], label=f"{label}.period_start")
        period_end = _iso_date(row["period_end"], label=f"{label}.period_end")
        if period_end < period_start:
            raise FDDContractError(f"{label}.period_end precedes period_start")
        adjustments.append(
            {
                "adjustment_id": _identifier(
                    row["adjustment_id"], label=f"{label}.adjustment_id"
                ),
                "economic_effect_id": _identifier(
                    row["economic_effect_id"],
                    label=f"{label}.economic_effect_id",
                ),
                "description": _text(row["description"], label=f"{label}.description"),
                "category_id": _identifier(
                    row["category_id"], label=f"{label}.category_id"
                ),
                "period_start": period_start,
                "period_end": period_end,
                "ebitda_impact": decimal_text(
                    _decimal(row["ebitda_impact"], label=f"{label}.ebitda_impact")
                ),
                "included": _boolean(row["included"], label=f"{label}.included"),
                "decision_ref": _closed_decision_ref(
                    row["decision_ref"],
                    label=f"{label}.decision_ref",
                    available_refs=decision_refs,
                ),
                "cash_effect": cash_effect,
                "evidence_refs": _normalize_evidence_refs(
                    row["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
            }
        )
    adjustments.sort(key=lambda item: item["adjustment_id"])
    _unique_rows(adjustments, "adjustment_id", label="adjustments")
    _unique_rows(adjustments, "economic_effect_id", label="adjustments")
    return {
        "reported_ebitda": _normalize_evidenced_amount(
            inputs["reported_ebitda"],
            label="inputs.reported_ebitda",
            available_refs=available_refs,
        ),
        "adjustments": adjustments,
    }


def _normalize_net_debt(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> dict[str, Any]:
    inputs = _mapping(value, label="inputs")
    _exact_fields(inputs, required={"as_of_date", "items"}, label="inputs")
    as_of_date = _iso_date(inputs["as_of_date"], label="inputs.as_of_date")
    items = []
    for index, raw_row in enumerate(_sequence(inputs["items"], label="items")):
        label = f"items[{index}]"
        row = _mapping(raw_row, label=label)
        _exact_fields(
            row,
            required={
                "amount",
                "as_of_date",
                "classification",
                "description",
                "decision_ref",
                "economic_effect_id",
                "evidence_refs",
                "included",
                "item_id",
            },
            label=label,
        )
        classification = _identifier(
            row["classification"], label=f"{label}.classification"
        )
        if classification not in _NET_DEBT_CLASSIFICATIONS:
            raise FDDContractError(f"{label}.classification is unsupported")
        item_as_of_date = _iso_date(row["as_of_date"], label=f"{label}.as_of_date")
        if item_as_of_date != as_of_date:
            raise FDDContractError(
                f"{label}.as_of_date does not match inputs.as_of_date"
            )
        items.append(
            {
                "item_id": _identifier(row["item_id"], label=f"{label}.item_id"),
                "economic_effect_id": _identifier(
                    row["economic_effect_id"],
                    label=f"{label}.economic_effect_id",
                ),
                "description": _text(row["description"], label=f"{label}.description"),
                "as_of_date": item_as_of_date,
                "classification": classification,
                "amount": decimal_text(
                    _non_negative_decimal(row["amount"], label=f"{label}.amount")
                ),
                "included": _boolean(row["included"], label=f"{label}.included"),
                "decision_ref": _closed_decision_ref(
                    row["decision_ref"],
                    label=f"{label}.decision_ref",
                    available_refs=decision_refs,
                ),
                "evidence_refs": _normalize_evidence_refs(
                    row["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
            }
        )
    items.sort(key=lambda item: item["item_id"])
    _unique_rows(items, "item_id", label="items")
    _unique_rows(items, "economic_effect_id", label="items")
    if not any(
        item["included"] and item["classification"] != "excluded" for item in items
    ):
        raise FDDContractError(
            "net-debt inputs require at least one included non-excluded item"
        )
    return {"as_of_date": as_of_date, "items": items}


def _normalize_working_capital(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> dict[str, Any]:
    inputs = _mapping(value, label="inputs")
    _exact_fields(
        inputs,
        required={
            "average_scale",
            "closing_period",
            "monthly_balances",
            "normalization_adjustments",
            "selected_target",
        },
        label="inputs",
    )
    average_scale = _non_negative_int(
        inputs["average_scale"], label="inputs.average_scale"
    )
    if average_scale > 6:
        raise FDDContractError("inputs.average_scale must not exceed 6")
    balances = []
    for index, raw_row in enumerate(
        _sequence(inputs["monthly_balances"], label="monthly_balances")
    ):
        label = f"monthly_balances[{index}]"
        row = _mapping(raw_row, label=label)
        _exact_fields(
            row,
            required={
                "evidence_refs",
                "included_in_average",
                "period",
                "period_end",
                "reported_operating_nwc",
            },
            label=label,
        )
        balances.append(
            {
                "period": _identifier(row["period"], label=f"{label}.period"),
                "period_end": _iso_date(row["period_end"], label=f"{label}.period_end"),
                "reported_operating_nwc": decimal_text(
                    _decimal(
                        row["reported_operating_nwc"],
                        label=f"{label}.reported_operating_nwc",
                    )
                ),
                "included_in_average": _boolean(
                    row["included_in_average"],
                    label=f"{label}.included_in_average",
                ),
                "evidence_refs": _normalize_evidence_refs(
                    row["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
            }
        )
    balances.sort(key=lambda item: (item["period_end"], item["period"]))
    _unique_rows(balances, "period", label="monthly_balances")
    _unique_rows(balances, "period_end", label="monthly_balances")
    if not balances or not any(item["included_in_average"] for item in balances):
        raise FDDContractError(
            "monthly_balances must include at least one average period"
        )
    periods = {item["period"] for item in balances}
    closing_period = _identifier(
        inputs["closing_period"], label="inputs.closing_period"
    )
    if closing_period not in periods:
        raise FDDContractError("inputs.closing_period is not in monthly_balances")

    adjustments = []
    for index, raw_row in enumerate(
        _sequence(
            inputs["normalization_adjustments"],
            label="normalization_adjustments",
        )
    ):
        label = f"normalization_adjustments[{index}]"
        row = _mapping(raw_row, label=label)
        _exact_fields(
            row,
            required={
                "adjustment_id",
                "category_id",
                "description",
                "decision_ref",
                "economic_effect_id",
                "evidence_refs",
                "included",
                "nwc_impact",
                "period",
            },
            label=label,
        )
        period = _identifier(row["period"], label=f"{label}.period")
        if period not in periods:
            raise FDDContractError(f"{label}.period is not in monthly_balances")
        adjustments.append(
            {
                "adjustment_id": _identifier(
                    row["adjustment_id"], label=f"{label}.adjustment_id"
                ),
                "economic_effect_id": _identifier(
                    row["economic_effect_id"],
                    label=f"{label}.economic_effect_id",
                ),
                "period": period,
                "description": _text(row["description"], label=f"{label}.description"),
                "category_id": _identifier(
                    row["category_id"], label=f"{label}.category_id"
                ),
                "nwc_impact": decimal_text(
                    _decimal(row["nwc_impact"], label=f"{label}.nwc_impact")
                ),
                "included": _boolean(row["included"], label=f"{label}.included"),
                "decision_ref": _closed_decision_ref(
                    row["decision_ref"],
                    label=f"{label}.decision_ref",
                    available_refs=decision_refs,
                ),
                "evidence_refs": _normalize_evidence_refs(
                    row["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
            }
        )
    adjustments.sort(key=lambda item: item["adjustment_id"])
    _unique_rows(
        adjustments,
        "adjustment_id",
        label="normalization_adjustments",
    )
    _unique_rows(
        adjustments,
        "economic_effect_id",
        label="normalization_adjustments",
    )
    target = _mapping(inputs["selected_target"], label="inputs.selected_target")
    _exact_fields(
        target,
        required={"amount", "basis", "decision_ref", "evidence_refs"},
        label="inputs.selected_target",
    )
    return {
        "monthly_balances": balances,
        "normalization_adjustments": adjustments,
        "closing_period": closing_period,
        "selected_target": {
            **_normalize_evidenced_amount(
                {
                    "amount": target["amount"],
                    "decision_ref": target["decision_ref"],
                    "evidence_refs": target["evidence_refs"],
                },
                label="inputs.selected_target",
                available_refs=available_refs,
                decision_refs=decision_refs,
            ),
            "basis": _text(target["basis"], label="inputs.selected_target.basis"),
        },
        "average_scale": average_scale,
    }


def _normalize_capex(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> dict[str, Any]:
    inputs = _mapping(value, label="inputs")
    _exact_fields(inputs, required={"items"}, label="inputs")
    items = []
    for index, raw_row in enumerate(_sequence(inputs["items"], label="items")):
        label = f"items[{index}]"
        row = _mapping(raw_row, label=label)
        _exact_fields(
            row,
            required={
                "amount",
                "capex_id",
                "classification",
                "description",
                "decision_ref",
                "economic_effect_id",
                "evidence_refs",
                "included",
                "measurement_basis",
                "period",
                "period_end",
                "period_start",
            },
            label=label,
        )
        basis = _identifier(
            row["measurement_basis"], label=f"{label}.measurement_basis"
        )
        if basis not in _CAPEX_BASES:
            raise FDDContractError(f"{label}.measurement_basis is unsupported")
        classification = _identifier(
            row["classification"], label=f"{label}.classification"
        )
        if classification not in _CAPEX_CLASSIFICATIONS:
            raise FDDContractError(f"{label}.classification is unsupported")
        items.append(
            {
                "capex_id": _identifier(row["capex_id"], label=f"{label}.capex_id"),
                "economic_effect_id": _identifier(
                    row["economic_effect_id"],
                    label=f"{label}.economic_effect_id",
                ),
                "period": _identifier(row["period"], label=f"{label}.period"),
                "period_start": _iso_date(
                    row["period_start"], label=f"{label}.period_start"
                ),
                "period_end": _iso_date(row["period_end"], label=f"{label}.period_end"),
                "description": _text(row["description"], label=f"{label}.description"),
                "measurement_basis": basis,
                "classification": classification,
                "amount": decimal_text(
                    _non_negative_decimal(row["amount"], label=f"{label}.amount")
                ),
                "included": _boolean(row["included"], label=f"{label}.included"),
                "decision_ref": _closed_decision_ref(
                    row["decision_ref"],
                    label=f"{label}.decision_ref",
                    available_refs=decision_refs,
                ),
                "evidence_refs": _normalize_evidence_refs(
                    row["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
            }
        )
        if items[-1]["period_end"] < items[-1]["period_start"]:
            raise FDDContractError(f"{label}.period_end precedes period_start")
    items.sort(key=lambda item: item["capex_id"])
    _unique_rows(items, "capex_id", label="items")
    _unique_rows(items, "economic_effect_id", label="items")
    if not any(
        item["included"] and item["classification"] != "excluded" for item in items
    ):
        raise FDDContractError(
            "Capex inputs require at least one included non-excluded item"
        )
    return {"items": items}


def _normalize_effect_refs(
    value: object,
    *,
    label: str,
    allow_empty: bool,
) -> list[str]:
    return sorted(_identifier_list(value, label=label, allow_empty=allow_empty))


def _validate_fdd_calculation_result_structure(
    value: object,
    *,
    expected_pack_id: str | None = None,
) -> dict[str, Any]:
    """Validate a sealed result before it can supply an upstream metric."""

    content = _sealed_content(
        value,
        schema_version="vera.fdd_calculation_result.v1",
        required={
            "calculation_policy",
            "case_ref",
            "case_sha256",
            "checks",
            "currency",
            "engine_version",
            "entity_refs",
            "limitations",
            "line_items",
            "metrics",
            "pack_id",
            "professional_review",
            "recipe_id",
            "report_ready",
            "reporting_period",
            "result_id",
            "scope_id",
            "source_tie_out",
            "source_artifacts",
            "status",
            "unit",
        },
        label="FDD calculation result",
    )
    pack_id = _identifier(content["pack_id"], label="pack_id")
    if expected_pack_id is not None and pack_id != expected_pack_id:
        raise FDDContractError(
            f"result pack_id {pack_id!r} does not match {expected_pack_id!r}"
        )
    if pack_id not in FDD_PACK_RECIPES:
        raise FDDContractError(f"unsupported FDD result pack: {pack_id}")
    if content["recipe_id"] != FDD_PACK_RECIPES[pack_id]:
        raise FDDContractError("result recipe_id does not match its pack")
    if content["engine_version"] != FDD_ENGINE_VERSION:
        raise FDDContractError(f"result engine_version must be {FDD_ENGINE_VERSION}")
    if content["status"] != "passed":
        raise FDDContractError("only passed FDD results can supply metrics")
    if content["report_ready"] is not False:
        raise FDDContractError("FDD calculation result cannot claim report readiness")
    case_ref = _identifier(content["case_ref"], label="case_ref")
    result_id = _identifier(content["result_id"], label="result_id")
    if result_id != f"{case_ref}.{pack_id}.result":
        raise FDDContractError("result_id does not close to case_ref and pack_id")

    metrics = []
    for index, raw_metric in enumerate(_sequence(content["metrics"], label="metrics")):
        label = f"metrics[{index}]"
        metric = _mapping(raw_metric, label=label)
        _exact_fields(
            metric,
            required={"economic_effect_refs", "metric_id", "value"},
            label=label,
        )
        metrics.append(
            {
                "metric_id": _identifier(
                    metric["metric_id"], label=f"{label}.metric_id"
                ),
                "value": decimal_text(
                    _decimal(metric["value"], label=f"{label}.value")
                ),
                "economic_effect_refs": _normalize_effect_refs(
                    metric["economic_effect_refs"],
                    label=f"{label}.economic_effect_refs",
                    allow_empty=True,
                ),
            }
        )
    _unique_rows(metrics, "metric_id", label="metrics")
    if not metrics:
        raise FDDContractError("FDD result must contain metrics")

    checks = []
    for index, raw_check in enumerate(_sequence(content["checks"], label="checks")):
        label = f"checks[{index}]"
        check = _mapping(raw_check, label=label)
        _exact_fields(
            check,
            required={"actual", "check_id", "difference", "expected", "status"},
            label=label,
        )
        if check["status"] != "passed":
            raise FDDContractError(f"{label}.status must be passed")
        expected = _decimal(check["expected"], label=f"{label}.expected")
        actual = _decimal(check["actual"], label=f"{label}.actual")
        difference = _decimal(check["difference"], label=f"{label}.difference")
        calculated_difference = _exact_sum([actual, _exact_negate(expected)])
        if difference != calculated_difference:
            raise FDDContractError(f"{label}.difference is stale")
        if difference != 0:
            raise FDDContractError(f"{label} is not a passed zero-difference identity")
        checks.append(
            {
                "check_id": _identifier(check["check_id"], label=f"{label}.check_id"),
                "status": "passed",
                "expected": decimal_text(expected),
                "actual": decimal_text(actual),
                "difference": decimal_text(difference),
            }
        )
    _unique_rows(checks, "check_id", label="checks")
    if not checks:
        raise FDDContractError("FDD result must contain calculation identities")

    line_items = [
        dict(_mapping(item, label=f"line_items[{index}]"))
        for index, item in enumerate(
            _sequence(content["line_items"], label="line_items")
        )
    ]
    policy = dict(_mapping(content["calculation_policy"], label="calculation_policy"))
    professional_review = _mapping(
        content["professional_review"], label="professional_review"
    )
    _exact_fields(
        professional_review,
        required={"boundary", "required", "status"},
        label="professional_review",
    )
    if (
        professional_review["required"] is not True
        or professional_review["status"] != "not_assessed"
    ):
        raise FDDContractError(
            "FDD results must retain the professional-review boundary"
        )
    source_tie_out = _mapping(content["source_tie_out"], label="source_tie_out")
    _exact_fields(
        source_tie_out,
        required={"boundary", "required", "status"},
        label="source_tie_out",
    )
    if (
        source_tie_out["required"] is not True
        or source_tie_out["status"] != "not_assessed"
    ):
        raise FDDContractError("FDD results must retain the source tie-out boundary")
    normalized = {
        "schema_version": "vera.fdd_calculation_result.v1",
        "result_id": result_id,
        "case_ref": case_ref,
        "case_sha256": _sha256(content["case_sha256"], label="case_sha256"),
        "pack_id": pack_id,
        "recipe_id": FDD_PACK_RECIPES[pack_id],
        "engine_version": FDD_ENGINE_VERSION,
        "status": "passed",
        "scope_id": _identifier(content["scope_id"], label="scope_id"),
        "entity_refs": sorted(
            _identifier_list(content["entity_refs"], label="entity_refs")
        ),
        "currency": _identifier(content["currency"], label="currency"),
        "unit": _identifier(content["unit"], label="unit"),
        "reporting_period": _normalize_period(content["reporting_period"]),
        "source_artifacts": _normalize_source_artifacts(content["source_artifacts"]),
        "metrics": metrics,
        "line_items": line_items,
        "checks": checks,
        "calculation_policy": policy,
        "source_tie_out": {
            "required": True,
            "status": "not_assessed",
            "boundary": _text(
                source_tie_out["boundary"],
                label="source_tie_out.boundary",
            ),
        },
        "professional_review": {
            "required": True,
            "status": "not_assessed",
            "boundary": _text(
                professional_review["boundary"],
                label="professional_review.boundary",
            ),
        },
        "limitations": _text_list(content["limitations"], label="limitations"),
        "report_ready": False,
    }
    if normalized != content:
        raise FDDContractError("FDD calculation result is not canonical")
    return _seal(normalized)


def validate_fdd_metric_receipt(value: object) -> dict[str, Any]:
    """Validate an immutable receipt for one metric from a sealed result."""

    content = _sealed_content(
        value,
        schema_version="vera.fdd_metric_receipt.v1",
        required={
            "case_ref",
            "case_sha256",
            "case",
            "currency",
            "economic_effect_refs",
            "engine_version",
            "metric_id",
            "pack_id",
            "receipt_id",
            "recipe_id",
            "reporting_period",
            "result_ref",
            "result_sha256",
            "source_artifacts",
            "unit",
            "value",
        },
        label="FDD metric receipt",
    )
    pack_id = _identifier(content["pack_id"], label="pack_id")
    if pack_id not in FDD_PACK_RECIPES:
        raise FDDContractError("metric receipt pack is unsupported")
    if content["recipe_id"] != FDD_PACK_RECIPES[pack_id]:
        raise FDDContractError("metric receipt recipe does not match its pack")
    if content["engine_version"] != FDD_ENGINE_VERSION:
        raise FDDContractError("metric receipt engine version is unsupported")
    case = validate_fdd_case(content["case"], expected_pack_id=pack_id)
    recomputed_result = execute_fdd_case(case, expected_pack_id=pack_id)
    result_ref = _identifier(content["result_ref"], label="result_ref")
    metric_id = _identifier(content["metric_id"], label="metric_id")
    receipt_id = _identifier(content["receipt_id"], label="receipt_id")
    if receipt_id != f"{result_ref}.{metric_id}":
        raise FDDContractError("metric receipt_id does not close")
    if content["case_ref"] != case["case_id"]:
        raise FDDContractError("metric receipt case_ref does not close")
    if content["case_sha256"] != case["content_sha256"]:
        raise FDDContractError("metric receipt case_sha256 does not close")
    if content["result_ref"] != recomputed_result["result_id"]:
        raise FDDContractError("metric receipt result_ref does not close")
    if content["result_sha256"] != recomputed_result["content_sha256"]:
        raise FDDContractError("metric receipt result_sha256 does not close")
    matching = [
        metric
        for metric in recomputed_result["metrics"]
        if metric["metric_id"] == metric_id
    ]
    if len(matching) != 1:
        raise FDDContractError(
            f"recomputed result does not contain metric {metric_id!r}"
        )
    recomputed_metric = matching[0]
    normalized = {
        "schema_version": "vera.fdd_metric_receipt.v1",
        "receipt_id": receipt_id,
        "result_ref": result_ref,
        "result_sha256": _sha256(content["result_sha256"], label="result_sha256"),
        "case_ref": _identifier(content["case_ref"], label="case_ref"),
        "case_sha256": _sha256(content["case_sha256"], label="case_sha256"),
        "case": case,
        "pack_id": pack_id,
        "recipe_id": FDD_PACK_RECIPES[pack_id],
        "engine_version": FDD_ENGINE_VERSION,
        "currency": _identifier(content["currency"], label="currency"),
        "unit": _identifier(content["unit"], label="unit"),
        "reporting_period": _normalize_period(content["reporting_period"]),
        "metric_id": metric_id,
        "value": decimal_text(_decimal(content["value"], label="value")),
        "economic_effect_refs": _normalize_effect_refs(
            content["economic_effect_refs"],
            label="economic_effect_refs",
            allow_empty=True,
        ),
        "source_artifacts": _normalize_source_artifacts(content["source_artifacts"]),
    }
    if normalized != content:
        raise FDDContractError("FDD metric receipt is not canonical")
    if (
        normalized["value"] != recomputed_metric["value"]
        or normalized["economic_effect_refs"]
        != recomputed_metric["economic_effect_refs"]
        or normalized["source_artifacts"] != recomputed_result["source_artifacts"]
        or normalized["currency"] != recomputed_result["currency"]
        or normalized["unit"] != recomputed_result["unit"]
        or normalized["reporting_period"] != recomputed_result["reporting_period"]
    ):
        raise FDDContractError("metric receipt differs from recomputed result")
    return _seal(normalized)


def build_fdd_metric_receipt(
    case: object,
    result: object,
    metric_id: str,
) -> dict[str, Any]:
    """Copy one exact metric and its provenance from a validated result."""

    validated_case = validate_fdd_case(case)
    validated = validate_fdd_calculation_result(
        result,
        case=validated_case,
        expected_pack_id=validated_case["pack_id"],
    )
    recomputed = execute_fdd_case(
        validated_case,
        expected_pack_id=validated_case["pack_id"],
    )
    if validated != recomputed:
        raise FDDContractError(
            "supplied result does not match deterministic case replay"
        )
    normalized_metric_id = _identifier(metric_id, label="metric_id")
    matching = [
        metric
        for metric in validated["metrics"]
        if metric["metric_id"] == normalized_metric_id
    ]
    if len(matching) != 1:
        raise FDDContractError(
            f"result must contain exactly one metric {normalized_metric_id!r}"
        )
    metric = matching[0]
    return validate_fdd_metric_receipt(
        _seal(
            {
                "schema_version": "vera.fdd_metric_receipt.v1",
                "receipt_id": (f"{validated['result_id']}.{normalized_metric_id}"),
                "result_ref": validated["result_id"],
                "result_sha256": validated["content_sha256"],
                "case_ref": validated["case_ref"],
                "case_sha256": validated["case_sha256"],
                "case": validated_case,
                "pack_id": validated["pack_id"],
                "recipe_id": validated["recipe_id"],
                "engine_version": validated["engine_version"],
                "currency": validated["currency"],
                "unit": validated["unit"],
                "reporting_period": dict(validated["reporting_period"]),
                "metric_id": normalized_metric_id,
                "value": metric["value"],
                "economic_effect_refs": list(metric["economic_effect_refs"]),
                "source_artifacts": [
                    dict(item) for item in validated["source_artifacts"]
                ],
            }
        )
    )


def _normalize_bridge_items(
    value: object,
    *,
    label: str,
    amount_field: str,
    available_refs: set[str],
    decision_refs: set[str],
    upstream_metrics: Mapping[str, Mapping[str, Any]],
    initial_effect_owners: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    items = []
    effect_owners = dict(initial_effect_owners or {})
    for index, raw_row in enumerate(_sequence(value, label=label)):
        row_label = f"{label}[{index}]"
        row = _mapping(raw_row, label=row_label)
        _exact_fields(
            row,
            required={
                "bridge_item_id",
                "category_id",
                "description",
                "decision_ref",
                "economic_effect_refs",
                "evidence_refs",
                "included",
                "upstream_metric_ref",
                "upstream_multiplier",
                amount_field,
            },
            label=row_label,
        )
        included = _boolean(row["included"], label=f"{row_label}.included")
        items.append(
            {
                "bridge_item_id": _identifier(
                    row["bridge_item_id"],
                    label=f"{row_label}.bridge_item_id",
                ),
                "description": _text(
                    row["description"], label=f"{row_label}.description"
                ),
                "category_id": _identifier(
                    row["category_id"], label=f"{row_label}.category_id"
                ),
                "economic_effect_refs": _normalize_effect_refs(
                    row["economic_effect_refs"],
                    label=f"{row_label}.economic_effect_refs",
                    allow_empty=not included,
                ),
                "included": included,
                "decision_ref": _closed_decision_ref(
                    row["decision_ref"],
                    label=f"{row_label}.decision_ref",
                    available_refs=decision_refs,
                ),
                "evidence_refs": _normalize_evidence_refs(
                    row["evidence_refs"],
                    label=f"{row_label}.evidence_refs",
                    available_refs=available_refs,
                ),
            }
        )
        normalized_row = items[-1]
        upstream_ref = row["upstream_metric_ref"]
        multiplier = row["upstream_multiplier"]
        declared_amount = _decimal(
            row[amount_field], label=f"{row_label}.{amount_field}"
        )
        if upstream_ref is None and multiplier is None:
            normalized_row["upstream_metric_ref"] = None
            normalized_row["upstream_multiplier"] = None
            normalized_row[amount_field] = decimal_text(declared_amount)
        elif upstream_ref is None or multiplier is None:
            raise FDDContractError(
                f"{row_label} upstream reference and multiplier must be paired"
            )
        else:
            receipt_ref = _identifier(
                upstream_ref,
                label=f"{row_label}.upstream_metric_ref",
            )
            if receipt_ref not in upstream_metrics:
                raise FDDContractError(f"{row_label}.upstream_metric_ref is unknown")
            multiplier_text = decimal_text(
                _decimal(
                    multiplier,
                    label=f"{row_label}.upstream_multiplier",
                )
            )
            if multiplier_text not in {"-1", "1"}:
                raise FDDContractError(
                    f"{row_label}.upstream_multiplier must be -1 or 1"
                )
            receipt = upstream_metrics[receipt_ref]
            expected_amount = _exact_product(
                _decimal(receipt["value"], label=f"{row_label}.upstream_value"),
                _decimal(multiplier_text, label=f"{row_label}.upstream_multiplier"),
            )
            if declared_amount != expected_amount:
                raise FDDContractError(
                    f"{row_label}.{amount_field} does not match its upstream metric"
                )
            if (
                normalized_row["economic_effect_refs"]
                != receipt["economic_effect_refs"]
            ):
                raise FDDContractError(
                    f"{row_label}.economic_effect_refs do not match upstream"
                )
            normalized_row["upstream_metric_ref"] = receipt_ref
            normalized_row["upstream_multiplier"] = multiplier_text
            normalized_row[amount_field] = decimal_text(expected_amount)
        if normalized_row["included"]:
            for effect_ref in normalized_row["economic_effect_refs"]:
                previous_owner = effect_owners.get(effect_ref)
                if previous_owner is not None:
                    raise FDDContractError(
                        f"{label} economic effect {effect_ref!r} is included by "
                        f"both {previous_owner!r} and "
                        f"{normalized_row['bridge_item_id']!r}"
                    )
                effect_owners[effect_ref] = normalized_row["bridge_item_id"]
    items.sort(key=lambda item: item["bridge_item_id"])
    _unique_rows(items, "bridge_item_id", label=label)
    return items


def _normalize_deal_bridges(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> dict[str, Any]:
    inputs = _mapping(value, label="inputs")
    _exact_fields(
        inputs,
        required={
            "adjusted_ebitda_ref",
            "cash_bridge_items",
            "enterprise_value",
            "equity_bridge_items",
            "upstream_metrics",
        },
        label="inputs",
    )
    upstream_metrics = [
        validate_fdd_metric_receipt(item)
        for item in _sequence(inputs["upstream_metrics"], label="upstream_metrics")
    ]
    upstream_metrics.sort(key=lambda item: item["receipt_id"])
    _unique_rows(upstream_metrics, "receipt_id", label="upstream_metrics")
    upstream_index = {item["receipt_id"]: item for item in upstream_metrics}
    adjusted_ebitda_ref = _identifier(
        inputs["adjusted_ebitda_ref"], label="inputs.adjusted_ebitda_ref"
    )
    try:
        adjusted_receipt = upstream_index[adjusted_ebitda_ref]
    except KeyError as exc:
        raise FDDContractError(
            "inputs.adjusted_ebitda_ref is not in upstream_metrics"
        ) from exc
    if (
        adjusted_receipt["pack_id"] != "quality_of_earnings"
        or adjusted_receipt["metric_id"] != "adjusted_ebitda"
    ):
        raise FDDContractError(
            "adjusted_ebitda_ref must identify a Quality of Earnings "
            "adjusted_ebitda metric"
        )
    cash_seed = {
        effect_ref: adjusted_ebitda_ref
        for effect_ref in adjusted_receipt["economic_effect_refs"]
    }
    return {
        "upstream_metrics": upstream_metrics,
        "adjusted_ebitda_ref": adjusted_ebitda_ref,
        "cash_bridge_items": _normalize_bridge_items(
            inputs["cash_bridge_items"],
            label="cash_bridge_items",
            amount_field="cash_flow_impact",
            available_refs=available_refs,
            decision_refs=decision_refs,
            upstream_metrics=upstream_index,
            initial_effect_owners=cash_seed,
        ),
        "enterprise_value": _normalize_evidenced_amount(
            inputs["enterprise_value"],
            label="inputs.enterprise_value",
            available_refs=available_refs,
            non_negative=True,
            decision_refs=decision_refs,
        ),
        "equity_bridge_items": _normalize_bridge_items(
            inputs["equity_bridge_items"],
            label="equity_bridge_items",
            amount_field="equity_value_impact",
            available_refs=available_refs,
            decision_refs=decision_refs,
            upstream_metrics=upstream_index,
        ),
    }


def _normalize_pack_inputs(
    pack_id: str,
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> dict[str, Any]:
    normalizers = {
        "quality_of_earnings": _normalize_quality_of_earnings,
        "net_debt": _normalize_net_debt,
        "normalized_working_capital": _normalize_working_capital,
        "capex": _normalize_capex,
        "deal_bridges": _normalize_deal_bridges,
    }
    try:
        normalizer = normalizers[pack_id]
    except KeyError as exc:
        raise FDDContractError(f"unsupported FDD pack: {pack_id}") from exc
    return normalizer(
        value,
        available_refs=available_refs,
        decision_refs=decision_refs,
    )


def _normalize_contract_refs(value: object) -> dict[str, Any]:
    refs = _mapping(value, label="contract_refs")
    _exact_fields(
        refs,
        required={
            "crosswalk_refs",
            "package_ref",
            "package_sha256",
            "relationship_refs",
            "request_ref",
        },
        label="contract_refs",
    )
    return {
        "package_ref": _identifier(
            refs["package_ref"], label="contract_refs.package_ref"
        ),
        "package_sha256": _sha256(
            refs["package_sha256"],
            label="contract_refs.package_sha256",
        ),
        "request_ref": _identifier(
            refs["request_ref"], label="contract_refs.request_ref"
        ),
        "relationship_refs": sorted(
            _identifier_list(
                refs["relationship_refs"],
                label="contract_refs.relationship_refs",
                allow_empty=True,
            )
        ),
        "crosswalk_refs": sorted(
            _identifier_list(
                refs["crosswalk_refs"],
                label="contract_refs.crosswalk_refs",
                allow_empty=True,
            )
        ),
    }


def _source_artifacts_from_package(
    package: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _normalize_source_artifacts(
        [
            {
                "artifact_ref": source["artifact_ref"],
                "dataset_contract_ref": source["dataset_contract_ref"],
                "role": "source_evidence",
                "byte_count": source["byte_count"],
                "sha256": source["sha256"],
            }
            for source in package["sources"]
        ]
    )


def _normalize_contract_stack(
    value: object,
    *,
    case_id: str,
    scope_id: str,
    entity_refs: Sequence[str],
    pack_id: str,
    currency: str,
    unit: str,
    reporting_period: Mapping[str, str],
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Validate the sealed case contracts and derive immutable case bindings."""

    stack = _mapping(value, label="contract_stack")
    _exact_fields(
        stack,
        required={
            "crosswalks",
            "datasets",
            "package",
            "relationships",
            "request",
        },
        label="contract_stack",
    )
    package = validate_data_package_manifest(stack["package"])
    datasets = [
        validate_dataset_contract(item)
        for item in _sequence(stack["datasets"], label="contract_stack.datasets")
    ]
    relationships = [
        validate_relationship_contract(item)
        for item in _sequence(
            stack["relationships"],
            label="contract_stack.relationships",
        )
    ]
    crosswalks = [
        validate_crosswalk_manifest(item)
        for item in _sequence(
            stack["crosswalks"],
            label="contract_stack.crosswalks",
        )
    ]
    request = validate_analysis_pack_request(stack["request"])
    datasets.sort(key=lambda item: item["dataset_contract_id"])
    relationships.sort(key=lambda item: item["relationship_id"])
    crosswalks.sort(key=lambda item: item["crosswalk_id"])
    _unique_rows(datasets, "dataset_contract_id", label="contract_stack.datasets")
    _unique_rows(
        relationships,
        "relationship_id",
        label="contract_stack.relationships",
    )
    _unique_rows(
        crosswalks,
        "crosswalk_id",
        label="contract_stack.crosswalks",
    )
    dataset_index = {item["dataset_contract_id"]: item for item in datasets}
    relationship_index = {item["relationship_id"]: item for item in relationships}
    crosswalk_index = {item["crosswalk_id"]: item for item in crosswalks}
    package_sources = {item["artifact_ref"]: item for item in package["sources"]}

    if request["pack_id"] != pack_id:
        raise FDDContractError("contract_stack request pack does not match case")
    if request["recipe_version"] != FDD_PACK_RECIPES[pack_id]:
        raise FDDContractError("contract_stack request recipe does not match case")
    for field in (
        "dataset_refs",
        "relationship_refs",
        "crosswalk_refs",
        "requested_outputs",
    ):
        if request[field] != sorted(request[field]):
            raise FDDContractError(f"contract_stack request {field} must be sorted")
    expected_parameters = {
        "case_id": case_id,
        "fdd_inputs_sha256": canonical_json_sha256(inputs),
        "scope_id": scope_id,
        "unit": unit,
    }
    if request["parameters"] != expected_parameters:
        raise FDDContractError(
            "contract_stack request parameters do not bind the FDD inputs"
        )
    if sorted(request["requested_outputs"]) != list(FDD_OUTPUT_ROLES):
        raise FDDContractError(
            "contract_stack request does not declare the fixed FDD outputs"
        )
    if set(request["dataset_refs"]) != set(dataset_index):
        raise FDDContractError("contract_stack request dataset references do not close")
    if set(request["relationship_refs"]) != set(relationship_index):
        raise FDDContractError(
            "contract_stack request relationship references do not close"
        )
    if set(request["crosswalk_refs"]) != set(crosswalk_index):
        raise FDDContractError(
            "contract_stack request crosswalk references do not close"
        )

    perimeter = package["reporting_perimeter"]
    if sorted(perimeter["entity_refs"]) != list(entity_refs):
        raise FDDContractError(
            "contract_stack package entities do not match the FDD case"
        )
    if perimeter["currency_refs"] != [currency]:
        raise FDDContractError(
            "FDD v1 requires exactly one package currency matching the case"
        )
    if reporting_period != {
        "start": perimeter["period_start"],
        "end": perimeter["period_end"],
    }:
        raise FDDContractError(
            "contract_stack package period does not match the FDD case"
        )
    package_dataset_refs = {
        source["dataset_contract_ref"] for source in package["sources"]
    }
    if package_dataset_refs != set(dataset_index):
        raise FDDContractError(
            "contract_stack package sources do not cover the requested datasets"
        )
    for dataset in datasets:
        expected_artifacts = {
            source["artifact_ref"]
            for source in package["sources"]
            if source["dataset_contract_ref"] == dataset["dataset_contract_id"]
        }
        actual_artifacts = set(dataset["source_artifact_refs"])
        if actual_artifacts != expected_artifacts:
            raise FDDContractError(
                f"dataset {dataset['dataset_contract_id']} artifact "
                "membership does not close to the package"
            )
        if (
            dataset["period"]["start"] > reporting_period["start"]
            or dataset["period"]["end"] < reporting_period["end"]
        ):
            raise FDDContractError(
                f"dataset {dataset['dataset_contract_id']} does not cover "
                "the FDD reporting period"
            )
        for field in dataset["fields"]:
            if field["currency"] is None:
                continue
            if field["currency"] != currency or field["unit"] != unit:
                raise FDDContractError(
                    f"dataset {dataset['dataset_contract_id']} field "
                    f"{field['name']} has a different currency or unit"
                )
    for relationship in relationships:
        left_ref = relationship["left_dataset_ref"]
        right_ref = relationship["right_dataset_ref"]
        if left_ref not in dataset_index or right_ref not in dataset_index:
            raise FDDContractError(
                f"relationship {relationship['relationship_id']} has "
                "unknown datasets"
            )
        left_fields = {field["name"] for field in dataset_index[left_ref]["fields"]}
        right_fields = {field["name"] for field in dataset_index[right_ref]["fields"]}
        if not set(relationship["left_keys"]) <= left_fields:
            raise FDDContractError(
                f"relationship {relationship['relationship_id']} has "
                "unknown left keys"
            )
        if not set(relationship["right_keys"]) <= right_fields:
            raise FDDContractError(
                f"relationship {relationship['relationship_id']} has "
                "unknown right keys"
            )
        crosswalk_ref = relationship["crosswalk_ref"]
        if crosswalk_ref is not None and crosswalk_ref not in crosswalk_index:
            raise FDDContractError(
                f"relationship {relationship['relationship_id']} has "
                "an unknown crosswalk"
            )
    for crosswalk in crosswalks:
        source_ref = crosswalk["source_dataset_ref"]
        target_ref = crosswalk["target_dataset_ref"]
        if source_ref not in dataset_index or target_ref not in dataset_index:
            raise FDDContractError(
                f"crosswalk {crosswalk['crosswalk_id']} has unknown datasets"
            )
        source_fields = {field["name"] for field in dataset_index[source_ref]["fields"]}
        target_fields = {field["name"] for field in dataset_index[target_ref]["fields"]}
        if not set(crosswalk["source_key_fields"]) <= source_fields:
            raise FDDContractError(
                f"crosswalk {crosswalk['crosswalk_id']} has unknown source keys"
            )
        if not set(crosswalk["target_key_fields"]) <= target_fields:
            raise FDDContractError(
                f"crosswalk {crosswalk['crosswalk_id']} has unknown target keys"
            )
        try:
            source_receipt = package_sources[crosswalk["artifact_ref"]]
        except KeyError as exc:
            raise FDDContractError(
                f"crosswalk {crosswalk['crosswalk_id']} artifact is "
                "outside the package"
            ) from exc
        if (
            crosswalk["artifact_sha256"] != source_receipt["sha256"]
            or crosswalk["byte_count"] != source_receipt["byte_count"]
        ):
            raise FDDContractError(
                f"crosswalk {crosswalk['crosswalk_id']} receipt is stale"
            )
    for relationship in relationships:
        crosswalk_ref = relationship["crosswalk_ref"]
        if crosswalk_ref is None:
            continue
        crosswalk = crosswalk_index[crosswalk_ref]
        if (
            crosswalk["source_dataset_ref"] != relationship["left_dataset_ref"]
            or crosswalk["target_dataset_ref"] != relationship["right_dataset_ref"]
            or crosswalk["source_key_fields"] != relationship["left_keys"]
            or crosswalk["target_key_fields"] != relationship["right_keys"]
        ):
            raise FDDContractError(
                f"relationship {relationship['relationship_id']} crosswalk "
                "mapping does not close"
            )
    normalized_stack = {
        "package": package,
        "datasets": datasets,
        "relationships": relationships,
        "crosswalks": crosswalks,
        "request": request,
    }
    contract_refs = {
        "package_ref": package["package_id"],
        "package_sha256": package["content_sha256"],
        "request_ref": request["request_id"],
        "relationship_refs": sorted(request["relationship_refs"]),
        "crosswalk_refs": sorted(request["crosswalk_refs"]),
    }
    return (
        normalized_stack,
        _normalize_contract_refs(contract_refs),
        _source_artifacts_from_package(package),
    )


def _validate_input_periods(
    *,
    pack_id: str,
    inputs: Mapping[str, Any],
    reporting_period: Mapping[str, str],
    case_id: str,
    scope_id: str,
    entity_refs: Sequence[str],
    contract_refs: Mapping[str, Any],
    currency: str,
    unit: str,
) -> None:
    start = reporting_period["start"]
    end = reporting_period["end"]

    def require_inside(item_start: str, item_end: str, *, label: str) -> None:
        if item_start < start or item_end > end:
            raise FDDContractError(f"{label} is outside the reporting period")

    if pack_id == "quality_of_earnings":
        for row in inputs["adjustments"]:
            require_inside(
                row["period_start"],
                row["period_end"],
                label=f"adjustment {row['adjustment_id']}",
            )
    elif pack_id == "net_debt":
        if not start <= inputs["as_of_date"] <= end:
            raise FDDContractError(
                "net debt as_of_date is outside the reporting period"
            )
    elif pack_id == "normalized_working_capital":
        for row in inputs["monthly_balances"]:
            if not start <= row["period_end"] <= end:
                raise FDDContractError(
                    f"working-capital period {row['period']} is outside "
                    "the reporting period"
                )
        closing = next(
            row
            for row in inputs["monthly_balances"]
            if row["period"] == inputs["closing_period"]
        )
        if closing["period_end"] != end:
            raise FDDContractError(
                "working-capital closing period must end on the reporting end date"
            )
    elif pack_id == "capex":
        for row in inputs["items"]:
            require_inside(
                row["period_start"],
                row["period_end"],
                label=f"Capex item {row['capex_id']}",
            )
    elif pack_id == "deal_bridges":
        for receipt in inputs["upstream_metrics"]:
            if receipt["case_ref"] != case_id:
                raise FDDContractError(
                    f"upstream metric {receipt['receipt_id']} belongs to "
                    "another case"
                )
            receipt_case = receipt["case"]
            if (
                receipt_case["scope_id"] != scope_id
                or receipt_case["entity_refs"] != list(entity_refs)
                or receipt_case["contract_refs"]["package_ref"]
                != contract_refs["package_ref"]
                or receipt_case["contract_refs"]["package_sha256"]
                != contract_refs["package_sha256"]
            ):
                raise FDDContractError(
                    f"upstream metric {receipt['receipt_id']} belongs to "
                    "another case context"
                )
            if receipt["currency"] != currency or receipt["unit"] != unit:
                raise FDDContractError(
                    f"upstream metric {receipt['receipt_id']} has a "
                    "different currency or unit"
                )
            if receipt["reporting_period"] != reporting_period:
                raise FDDContractError(
                    f"upstream metric {receipt['receipt_id']} has a "
                    "different reporting period"
                )


def validate_fdd_case(
    value: object,
    *,
    expected_pack_id: str | None = None,
) -> dict[str, Any]:
    """Validate one reviewed, sealed FDD calculation case."""

    content = _sealed_content(
        value,
        schema_version="vera.fdd_preparation_case.v1",
        required={
            "case_id",
            "contract_refs",
            "contract_stack",
            "currency",
            "engine_version",
            "entity_refs",
            "inputs",
            "limitations",
            "pack_id",
            "recipe_id",
            "report_ready",
            "reporting_period",
            "review",
            "reviewed_decisions",
            "scope_id",
            "source_artifacts",
            "unit",
        },
        label="FDD preparation case",
    )
    pack_id = _identifier(content["pack_id"], label="pack_id")
    if expected_pack_id is not None and pack_id != expected_pack_id:
        raise FDDContractError(
            f"case pack_id {pack_id!r} does not match {expected_pack_id!r}"
        )
    if pack_id not in FDD_PACK_RECIPES:
        raise FDDContractError(f"unsupported FDD pack: {pack_id}")
    if content["recipe_id"] != FDD_PACK_RECIPES[pack_id]:
        raise FDDContractError("recipe_id does not match the registered FDD pack")
    if content["engine_version"] != FDD_ENGINE_VERSION:
        raise FDDContractError(f"engine_version must be {FDD_ENGINE_VERSION}")
    if content["report_ready"] is not False:
        raise FDDContractError("FDD preparation cannot claim report readiness")
    stack_preview = _mapping(content["contract_stack"], label="contract_stack")
    _exact_fields(
        stack_preview,
        required={
            "crosswalks",
            "datasets",
            "package",
            "relationships",
            "request",
        },
        label="contract_stack",
    )
    package_preview = validate_data_package_manifest(stack_preview["package"])
    preview_artifacts = _source_artifacts_from_package(package_preview)
    available_refs = {item["artifact_ref"] for item in preview_artifacts}
    decisions = _normalize_reviewed_decisions(content["reviewed_decisions"])
    decision_refs = {item["decision_ref"] for item in decisions}
    reporting_period = _normalize_period(content["reporting_period"])
    case_id = _identifier(content["case_id"], label="case_id")
    scope_id = _identifier(content["scope_id"], label="scope_id")
    entity_refs = sorted(_identifier_list(content["entity_refs"], label="entity_refs"))
    currency = _identifier(content["currency"], label="currency")
    unit = _identifier(content["unit"], label="unit")
    normalized_inputs = _normalize_pack_inputs(
        pack_id,
        content["inputs"],
        available_refs=available_refs,
        decision_refs=decision_refs,
    )
    contract_stack, contract_refs, artifacts = _normalize_contract_stack(
        content["contract_stack"],
        case_id=case_id,
        scope_id=scope_id,
        entity_refs=entity_refs,
        pack_id=pack_id,
        currency=currency,
        unit=unit,
        reporting_period=reporting_period,
        inputs=normalized_inputs,
    )
    if _normalize_contract_refs(content["contract_refs"]) != contract_refs:
        raise FDDContractError("FDD case contract_refs are stale")
    if _normalize_source_artifacts(content["source_artifacts"]) != artifacts:
        raise FDDContractError("FDD case source_artifacts are stale")
    _validate_input_periods(
        pack_id=pack_id,
        inputs=normalized_inputs,
        reporting_period=reporting_period,
        case_id=case_id,
        scope_id=scope_id,
        entity_refs=entity_refs,
        contract_refs=contract_refs,
        currency=currency,
        unit=unit,
    )
    normalized = {
        "schema_version": "vera.fdd_preparation_case.v1",
        "case_id": case_id,
        "scope_id": scope_id,
        "entity_refs": entity_refs,
        "pack_id": pack_id,
        "recipe_id": FDD_PACK_RECIPES[pack_id],
        "engine_version": FDD_ENGINE_VERSION,
        "currency": currency,
        "unit": unit,
        "reporting_period": reporting_period,
        "contract_refs": contract_refs,
        "contract_stack": contract_stack,
        "source_artifacts": artifacts,
        "review": _normalize_review(content["review"]),
        "reviewed_decisions": decisions,
        "inputs": normalized_inputs,
        "limitations": _text_list(content["limitations"], label="limitations"),
        "report_ready": False,
    }
    if normalized != content:
        raise FDDContractError("FDD preparation case is not canonical")
    return _seal(normalized)


def build_fdd_case(
    *,
    case_id: str,
    scope_id: str,
    entity_refs: Sequence[str],
    pack_id: str,
    currency: str,
    unit: str,
    reporting_period: Mapping[str, Any],
    package: Mapping[str, Any],
    datasets: Sequence[Mapping[str, Any]],
    request_id: str,
    review: Mapping[str, Any],
    reviewed_decisions: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
    relationships: Sequence[Mapping[str, Any]] = (),
    crosswalks: Sequence[Mapping[str, Any]] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build and seal one reviewed FDD calculation case."""

    if pack_id not in FDD_PACK_RECIPES:
        raise FDDContractError(f"unsupported FDD pack: {pack_id}")
    package_preview = validate_data_package_manifest(package)
    artifacts = _source_artifacts_from_package(package_preview)
    decisions = _normalize_reviewed_decisions(reviewed_decisions)
    normalized_inputs = _normalize_pack_inputs(
        pack_id,
        inputs,
        available_refs={item["artifact_ref"] for item in artifacts},
        decision_refs={item["decision_ref"] for item in decisions},
    )
    normalized_case_id = _identifier(case_id, label="case_id")
    normalized_scope_id = _identifier(scope_id, label="scope_id")
    normalized_entity_refs = sorted(_identifier_list(entity_refs, label="entity_refs"))
    normalized_currency = _identifier(currency, label="currency")
    normalized_unit = _identifier(unit, label="unit")
    normalized_period = _normalize_period(reporting_period)
    validated_datasets = [validate_dataset_contract(item) for item in datasets]
    validated_relationships = [
        validate_relationship_contract(item) for item in relationships
    ]
    validated_crosswalks = [validate_crosswalk_manifest(item) for item in crosswalks]
    request = build_analysis_pack_request(
        request_id=request_id,
        pack_id=pack_id,
        recipe_version=FDD_PACK_RECIPES[pack_id],
        dataset_refs=sorted(item["dataset_contract_id"] for item in validated_datasets),
        relationship_refs=sorted(
            item["relationship_id"] for item in validated_relationships
        ),
        crosswalk_refs=sorted(item["crosswalk_id"] for item in validated_crosswalks),
        parameters={
            "case_id": normalized_case_id,
            "fdd_inputs_sha256": canonical_json_sha256(normalized_inputs),
            "scope_id": normalized_scope_id,
            "unit": normalized_unit,
        },
        requested_outputs=FDD_OUTPUT_ROLES,
    )
    contract_stack = {
        "package": package_preview,
        "datasets": validated_datasets,
        "relationships": validated_relationships,
        "crosswalks": validated_crosswalks,
        "request": request,
    }
    normalized_stack, contract_refs, artifacts = _normalize_contract_stack(
        contract_stack,
        case_id=normalized_case_id,
        scope_id=normalized_scope_id,
        entity_refs=normalized_entity_refs,
        pack_id=pack_id,
        currency=normalized_currency,
        unit=normalized_unit,
        reporting_period=normalized_period,
        inputs=normalized_inputs,
    )
    return validate_fdd_case(
        _seal(
            {
                "schema_version": "vera.fdd_preparation_case.v1",
                "case_id": normalized_case_id,
                "scope_id": normalized_scope_id,
                "entity_refs": normalized_entity_refs,
                "pack_id": pack_id,
                "recipe_id": FDD_PACK_RECIPES[pack_id],
                "engine_version": FDD_ENGINE_VERSION,
                "currency": normalized_currency,
                "unit": normalized_unit,
                "reporting_period": normalized_period,
                "contract_refs": contract_refs,
                "contract_stack": normalized_stack,
                "source_artifacts": artifacts,
                "review": _normalize_review(review),
                "reviewed_decisions": decisions,
                "inputs": normalized_inputs,
                "limitations": _text_list(limitations, label="limitations"),
                "report_ready": False,
            }
        )
    )


def _metric(
    metric_id: str,
    value: Decimal,
    economic_effect_refs: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": decimal_text(value),
        "economic_effect_refs": sorted(economic_effect_refs),
    }


def _execute_quality_of_earnings(inputs: Mapping[str, Any]) -> dict[str, Any]:
    reported = _decimal(
        inputs["reported_ebitda"]["amount"],
        label="reported_ebitda.amount",
    )
    included_rows = [row for row in inputs["adjustments"] if row["included"]]
    included_effects = [row["economic_effect_id"] for row in included_rows]
    included = _exact_sum(
        [_decimal(row["ebitda_impact"], label="ebitda_impact") for row in included_rows]
    )
    adjusted = _exact_sum([reported, included])
    return {
        "metrics": [
            _metric("reported_ebitda", reported),
            _metric("included_adjustments", included, included_effects),
            _metric("adjusted_ebitda", adjusted, included_effects),
        ],
        "line_items": [dict(row) for row in inputs["adjustments"]],
        "checks": [
            {
                "check_id": "adjusted_ebitda_identity",
                "status": "passed",
                "expected": decimal_text(adjusted),
                "actual": decimal_text(_exact_sum([reported, included])),
                "difference": "0",
            }
        ],
    }


def _execute_net_debt(inputs: Mapping[str, Any]) -> dict[str, Any]:
    amounts: dict[str, list[Decimal]] = defaultdict(list)
    effects: dict[str, list[str]] = defaultdict(list)
    for row in inputs["items"]:
        if row["included"] and row["classification"] != "excluded":
            amounts[row["classification"]].append(
                _non_negative_decimal(row["amount"], label="amount")
            )
            effects[row["classification"]].append(row["economic_effect_id"])
    totals = {
        classification: _exact_sum(amounts[classification])
        for classification in _NET_DEBT_CLASSIFICATIONS
    }
    gross_effects = sorted(effects["debt"] + effects["debt_like"])
    liquidity_effects = sorted(effects["cash"] + effects["cash_like"])
    all_effects = sorted(gross_effects + liquidity_effects)
    gross = _exact_sum([totals["debt"], totals["debt_like"]])
    liquidity = _exact_sum([totals["cash"], totals["cash_like"]])
    net_debt = _exact_sum([gross, _exact_negate(liquidity)])
    return {
        "metrics": [
            _metric("cash", totals["cash"], effects["cash"]),
            _metric("cash_like", totals["cash_like"], effects["cash_like"]),
            _metric("debt", totals["debt"], effects["debt"]),
            _metric("debt_like", totals["debt_like"], effects["debt_like"]),
            _metric("gross_debt_and_debt_like", gross, gross_effects),
            _metric("net_debt", net_debt, all_effects),
        ],
        "line_items": [dict(row) for row in inputs["items"]],
        "checks": [
            {
                "check_id": "net_debt_identity",
                "status": "passed",
                "expected": decimal_text(net_debt),
                "actual": decimal_text(_exact_sum([gross, _exact_negate(liquidity)])),
                "difference": "0",
            }
        ],
        "calculation_policy": {"as_of_date": inputs["as_of_date"]},
    }


def _rounded_average(values: Sequence[Decimal], *, scale: int) -> Decimal:
    total = _exact_sum(values)
    coefficient, exponent = _decimal_components(total)
    power = exponent + scale
    numerator = coefficient * (10**power) if power >= 0 else coefficient
    denominator = len(values) if power >= 0 else len(values) * (10 ** (-power))
    rounded, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        rounded += 1
    if numerator < 0:
        rounded = -rounded
    return _decimal_from_components(rounded, -scale)


def _execute_working_capital(inputs: Mapping[str, Any]) -> dict[str, Any]:
    adjustment_values: dict[str, list[Decimal]] = defaultdict(list)
    adjustment_effects: dict[str, list[str]] = defaultdict(list)
    for row in inputs["normalization_adjustments"]:
        if row["included"]:
            adjustment_values[row["period"]].append(
                _decimal(row["nwc_impact"], label="nwc_impact")
            )
            adjustment_effects[row["period"]].append(row["economic_effect_id"])
    lines = []
    normalized_by_period = {}
    average_values = []
    for row in inputs["monthly_balances"]:
        reported = _decimal(
            row["reported_operating_nwc"],
            label="reported_operating_nwc",
        )
        adjustment = _exact_sum(adjustment_values[row["period"]])
        normalized = _exact_sum([reported, adjustment])
        normalized_by_period[row["period"]] = normalized
        if row["included_in_average"]:
            average_values.append(normalized)
        lines.append(
            {
                **dict(row),
                "normalization_adjustment": decimal_text(adjustment),
                "normalized_operating_nwc": decimal_text(normalized),
            }
        )
    candidate_average = _rounded_average(
        average_values,
        scale=inputs["average_scale"],
    )
    selected_target = _decimal(
        inputs["selected_target"]["amount"],
        label="selected_target.amount",
    )
    closing = normalized_by_period[inputs["closing_period"]]
    closing_adjustment = _exact_sum([closing, _exact_negate(selected_target)])
    average_periods = {
        row["period"]
        for row in inputs["monthly_balances"]
        if row["included_in_average"]
    }
    average_effects = sorted(
        effect for period in average_periods for effect in adjustment_effects[period]
    )
    closing_effects = sorted(adjustment_effects[inputs["closing_period"]])
    return {
        "metrics": [
            _metric(
                "candidate_average_normalized_nwc",
                candidate_average,
                average_effects,
            ),
            _metric("selected_target_nwc", selected_target),
            _metric("closing_normalized_nwc", closing, closing_effects),
            _metric(
                "closing_vs_target_adjustment",
                closing_adjustment,
                closing_effects,
            ),
        ],
        "line_items": lines,
        "checks": [
            {
                "check_id": "closing_vs_target_identity",
                "status": "passed",
                "expected": decimal_text(closing_adjustment),
                "actual": decimal_text(
                    _exact_sum([closing, _exact_negate(selected_target)])
                ),
                "difference": "0",
            }
        ],
        "calculation_policy": {
            "average_scale": inputs["average_scale"],
            "average_rounding": "half_up",
            "target_basis": inputs["selected_target"]["basis"],
            "closing_period": inputs["closing_period"],
        },
    }


def _execute_capex(inputs: Mapping[str, Any]) -> dict[str, Any]:
    grouped_amounts: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    grouped_effects: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in inputs["items"]:
        if not row["included"] or row["classification"] == "excluded":
            continue
        amount = _non_negative_decimal(row["amount"], label="amount")
        key = (row["measurement_basis"], row["classification"])
        grouped_amounts[key].append(amount)
        grouped_effects[key].append(row["economic_effect_id"])
    totals = {key: _exact_sum(values) for key, values in grouped_amounts.items()}
    bases = sorted({basis for basis, _ in totals})
    basis_totals = {
        basis: _exact_sum(
            [
                amount
                for (item_basis, _), amount in totals.items()
                if item_basis == basis
            ]
        )
        for basis in bases
    }
    basis_effects = {
        basis: sorted(
            effect
            for (item_basis, _), effects in grouped_effects.items()
            if item_basis == basis
            for effect in effects
        )
        for basis in bases
    }
    metrics = [
        _metric(f"capex.{basis}.total", amount, basis_effects[basis])
        for basis, amount in sorted(basis_totals.items())
    ]
    metrics.extend(
        _metric(
            f"capex.{basis}.{classification}",
            amount,
            grouped_effects[(basis, classification)],
        )
        for (basis, classification), amount in sorted(totals.items())
    )
    return {
        "metrics": metrics,
        "line_items": [dict(row) for row in inputs["items"]],
        "checks": [
            {
                "check_id": f"capex_{basis}_classification_footing",
                "status": "passed",
                "expected": decimal_text(total),
                "actual": decimal_text(
                    _exact_sum(
                        [
                            amount
                            for (item_basis, _), amount in totals.items()
                            if item_basis == basis
                        ]
                    )
                ),
                "difference": "0",
            }
            for basis, total in sorted(basis_totals.items())
        ],
    }


def _execute_deal_bridges(inputs: Mapping[str, Any]) -> dict[str, Any]:
    upstream_index = {item["receipt_id"]: item for item in inputs["upstream_metrics"]}
    adjusted_receipt = upstream_index[inputs["adjusted_ebitda_ref"]]
    adjusted_ebitda = _decimal(adjusted_receipt["value"], label="adjusted_ebitda")
    included_cash_rows = [row for row in inputs["cash_bridge_items"] if row["included"]]
    cash_impacts = _exact_sum(
        [
            _decimal(row["cash_flow_impact"], label="cash_flow_impact")
            for row in included_cash_rows
        ]
    )
    cash_effects = sorted(
        effect for row in included_cash_rows for effect in row["economic_effect_refs"]
    )
    cash_result_effects = sorted(
        adjusted_receipt["economic_effect_refs"] + cash_effects
    )
    cash_bridge_result = _exact_sum([adjusted_ebitda, cash_impacts])
    enterprise_value = _non_negative_decimal(
        inputs["enterprise_value"]["amount"],
        label="enterprise_value.amount",
    )
    included_equity_rows = [
        row for row in inputs["equity_bridge_items"] if row["included"]
    ]
    equity_impacts = _exact_sum(
        [
            _decimal(row["equity_value_impact"], label="equity_value_impact")
            for row in included_equity_rows
        ]
    )
    equity_effects = sorted(
        effect for row in included_equity_rows for effect in row["economic_effect_refs"]
    )
    equity_value = _exact_sum([enterprise_value, equity_impacts])
    return {
        "metrics": [
            _metric(
                "adjusted_ebitda",
                adjusted_ebitda,
                adjusted_receipt["economic_effect_refs"],
            ),
            _metric("cash_bridge_adjustments", cash_impacts, cash_effects),
            _metric(
                "cash_bridge_result",
                cash_bridge_result,
                cash_result_effects,
            ),
            _metric("enterprise_value_input", enterprise_value),
            _metric(
                "equity_bridge_adjustments",
                equity_impacts,
                equity_effects,
            ),
            _metric("equity_value", equity_value, equity_effects),
        ],
        "line_items": [
            *[
                {**dict(row), "bridge": "ebitda_to_cash"}
                for row in inputs["cash_bridge_items"]
            ],
            *[
                {**dict(row), "bridge": "enterprise_to_equity"}
                for row in inputs["equity_bridge_items"]
            ],
        ],
        "checks": [
            {
                "check_id": "ebitda_to_cash_identity",
                "status": "passed",
                "expected": decimal_text(cash_bridge_result),
                "actual": decimal_text(_exact_sum([adjusted_ebitda, cash_impacts])),
                "difference": "0",
            },
            {
                "check_id": "enterprise_to_equity_identity",
                "status": "passed",
                "expected": decimal_text(equity_value),
                "actual": decimal_text(_exact_sum([enterprise_value, equity_impacts])),
                "difference": "0",
            },
        ],
    }


def execute_fdd_case(
    value: object,
    *,
    expected_pack_id: str | None = None,
) -> dict[str, Any]:
    """Execute one fixed FDD recipe from a reviewed case."""

    case = validate_fdd_case(value, expected_pack_id=expected_pack_id)
    executors = {
        "quality_of_earnings": _execute_quality_of_earnings,
        "net_debt": _execute_net_debt,
        "normalized_working_capital": _execute_working_capital,
        "capex": _execute_capex,
        "deal_bridges": _execute_deal_bridges,
    }
    calculated = executors[case["pack_id"]](case["inputs"])
    calculation_policy = dict(calculated.pop("calculation_policy", {}))
    result = {
        "schema_version": "vera.fdd_calculation_result.v1",
        "result_id": f"{case['case_id']}.{case['pack_id']}.result",
        "case_ref": case["case_id"],
        "case_sha256": case["content_sha256"],
        "pack_id": case["pack_id"],
        "recipe_id": case["recipe_id"],
        "engine_version": FDD_ENGINE_VERSION,
        "status": "passed",
        "scope_id": case["scope_id"],
        "entity_refs": list(case["entity_refs"]),
        "currency": case["currency"],
        "unit": case["unit"],
        "reporting_period": dict(case["reporting_period"]),
        "source_artifacts": [dict(item) for item in case["source_artifacts"]],
        **calculated,
        "calculation_policy": calculation_policy,
        "source_tie_out": {
            "required": True,
            "status": "not_assessed",
            "boundary": (
                "Artifact receipts and evidence references are bound, but "
                "source values are not independently recomputed from bytes."
            ),
        },
        "professional_review": {
            "required": True,
            "status": "not_assessed",
            "boundary": (
                "Mechanical preparation only; accounting treatment and deal "
                "conclusions require professional review."
            ),
        },
        "limitations": list(case["limitations"]),
        "report_ready": False,
    }
    return _validate_fdd_calculation_result_structure(_seal(result))


def validate_fdd_calculation_result(
    value: object,
    *,
    case: object,
    expected_pack_id: str | None = None,
) -> dict[str, Any]:
    """Validate a result by replaying the exact sealed FDD case."""

    validated_case = validate_fdd_case(
        case,
        expected_pack_id=expected_pack_id,
    )
    validated_result = _validate_fdd_calculation_result_structure(
        value,
        expected_pack_id=validated_case["pack_id"],
    )
    replayed_result = execute_fdd_case(
        validated_case,
        expected_pack_id=validated_case["pack_id"],
    )
    if validated_result != replayed_result:
        raise FDDContractError(
            "FDD calculation result does not match deterministic replay"
        )
    return validated_result


def _normalize_amount_basis(
    value: object,
    *,
    label: str,
    non_negative: bool = True,
) -> dict[str, Any]:
    basis = _mapping(value, label=label)
    _exact_fields(
        basis,
        required={"status", "amount", "low", "high"},
        label=label,
    )
    status = _identifier(basis["status"], label=f"{label}.status")
    if status not in _AMOUNT_STATUSES:
        raise FDDContractError(f"{label}.status is unsupported")
    amount = basis["amount"]
    low = basis["low"]
    high = basis["high"]
    if status == "exact":
        if low is not None or high is not None:
            raise FDDContractError(f"{label} exact amount cannot include a range")
        parser = _non_negative_decimal if non_negative else _decimal
        normalized_amount = decimal_text(parser(amount, label=f"{label}.amount"))
        return {
            "status": status,
            "amount": normalized_amount,
            "low": None,
            "high": None,
        }
    if status == "range":
        if amount is not None:
            raise FDDContractError(f"{label} range cannot include an exact amount")
        parser = _non_negative_decimal if non_negative else _decimal
        normalized_low = parser(low, label=f"{label}.low")
        normalized_high = parser(high, label=f"{label}.high")
        if normalized_high < normalized_low:
            raise FDDContractError(f"{label}.high is below low")
        return {
            "status": status,
            "amount": None,
            "low": decimal_text(normalized_low),
            "high": decimal_text(normalized_high),
        }
    if amount is not None or low is not None or high is not None:
        raise FDDContractError(f"{label} unquantified amount must remain null")
    return {"status": status, "amount": None, "low": None, "high": None}


def _normalize_register_header(
    content: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    set[str],
    dict[str, str],
    list[dict[str, str]],
    set[str],
]:
    case = validate_fdd_case(content["case"])
    artifacts = _normalize_source_artifacts(content["source_artifacts"])
    expected_header = {
        "case_ref": case["case_id"],
        "scope_id": case["scope_id"],
        "entity_refs": case["entity_refs"],
        "package_ref": case["contract_refs"]["package_ref"],
        "package_sha256": case["contract_refs"]["package_sha256"],
        "currency": case["currency"],
        "unit": case["unit"],
        "reporting_period": case["reporting_period"],
        "source_artifacts": case["source_artifacts"],
    }
    observed_header = {
        "case_ref": _identifier(content["case_ref"], label="case_ref"),
        "scope_id": _identifier(content["scope_id"], label="scope_id"),
        "entity_refs": sorted(
            _identifier_list(content["entity_refs"], label="entity_refs")
        ),
        "package_ref": _identifier(content["package_ref"], label="package_ref"),
        "package_sha256": _sha256(content["package_sha256"], label="package_sha256"),
        "currency": _identifier(content["currency"], label="currency"),
        "unit": _identifier(content["unit"], label="unit"),
        "reporting_period": _normalize_period(content["reporting_period"]),
        "source_artifacts": artifacts,
    }
    for field, expected in expected_header.items():
        if observed_header[field] != expected:
            raise FDDContractError(
                f"register {field} does not close to the sealed FDD case"
            )
    decisions = _normalize_reviewed_decisions(content["reviewed_decisions"])
    return (
        case,
        artifacts,
        {item["artifact_ref"] for item in artifacts},
        _normalize_review(content["review"]),
        decisions,
        {item["decision_ref"] for item in decisions},
    )


def _normalize_register_completeness(
    value: object,
    *,
    label: str,
) -> dict[str, str]:
    completeness = _mapping(value, label=label)
    _exact_fields(
        completeness,
        required={"boundary", "status"},
        label=label,
    )
    if completeness["status"] != "not_assessed":
        raise FDDContractError(f"{label}.status must remain not_assessed in v1")
    return {
        "status": "not_assessed",
        "boundary": _text(completeness["boundary"], label=f"{label}.boundary"),
    }


def _normalize_contingency_items(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
) -> list[dict[str, Any]]:
    items = []
    for index, raw_item in enumerate(_sequence(value, label="items")):
        label = f"items[{index}]"
        item = _mapping(raw_item, label=label)
        _exact_fields(
            item,
            required={
                "amount_basis",
                "category_id",
                "contingency_id",
                "deal_treatment_id",
                "decision_ref",
                "description",
                "economic_effect_id",
                "evidence_refs",
                "open_questions",
                "owner_ref",
                "status_id",
                "title",
            },
            label=label,
        )
        items.append(
            {
                "contingency_id": _identifier(
                    item["contingency_id"], label=f"{label}.contingency_id"
                ),
                "economic_effect_id": _identifier(
                    item["economic_effect_id"],
                    label=f"{label}.economic_effect_id",
                ),
                "title": _text(item["title"], label=f"{label}.title"),
                "description": _text(item["description"], label=f"{label}.description"),
                "category_id": _identifier(
                    item["category_id"], label=f"{label}.category_id"
                ),
                "amount_basis": _normalize_amount_basis(
                    item["amount_basis"], label=f"{label}.amount_basis"
                ),
                "status_id": _identifier(item["status_id"], label=f"{label}.status_id"),
                "deal_treatment_id": _identifier(
                    item["deal_treatment_id"],
                    label=f"{label}.deal_treatment_id",
                ),
                "decision_ref": _closed_decision_ref(
                    item["decision_ref"],
                    label=f"{label}.decision_ref",
                    available_refs=decision_refs,
                ),
                "owner_ref": _identifier(item["owner_ref"], label=f"{label}.owner_ref"),
                "evidence_refs": _normalize_evidence_refs(
                    item["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
                "open_questions": _text_list(
                    item["open_questions"], label=f"{label}.open_questions"
                ),
            }
        )
    items.sort(key=lambda item: item["contingency_id"])
    _unique_rows(items, "contingency_id", label="items")
    _unique_rows(items, "economic_effect_id", label="items")
    return items


def validate_contingent_liability_register(value: object) -> dict[str, Any]:
    """Validate a reviewed contingency register without assessing completeness."""

    content = _sealed_content(
        value,
        schema_version="vera.contingent_liability_register.v1",
        required={
            "case",
            "case_ref",
            "completeness",
            "currency",
            "entity_refs",
            "items",
            "limitations",
            "package_ref",
            "package_sha256",
            "register_id",
            "report_ready",
            "reporting_period",
            "review",
            "reviewed_decisions",
            "scope_id",
            "source_artifacts",
            "unit",
        },
        label="contingent liability register",
    )
    if content["report_ready"] is not False:
        raise FDDContractError("contingency register cannot claim report readiness")
    (
        case,
        artifacts,
        available_refs,
        review,
        decisions,
        decision_refs,
    ) = _normalize_register_header(content)
    items = _normalize_contingency_items(
        content["items"],
        available_refs=available_refs,
        decision_refs=decision_refs,
    )
    normalized = {
        "schema_version": "vera.contingent_liability_register.v1",
        "register_id": _identifier(content["register_id"], label="register_id"),
        "case": case,
        "case_ref": case["case_id"],
        "scope_id": case["scope_id"],
        "entity_refs": case["entity_refs"],
        "package_ref": case["contract_refs"]["package_ref"],
        "package_sha256": case["contract_refs"]["package_sha256"],
        "currency": case["currency"],
        "unit": case["unit"],
        "reporting_period": case["reporting_period"],
        "source_artifacts": artifacts,
        "review": review,
        "reviewed_decisions": decisions,
        "completeness": _normalize_register_completeness(
            content["completeness"],
            label="completeness",
        ),
        "items": items,
        "limitations": _text_list(content["limitations"], label="limitations"),
        "report_ready": False,
    }
    if normalized != content:
        raise FDDContractError("contingent liability register is not canonical")
    return _seal(normalized)


def build_contingent_liability_register(
    *,
    register_id: str,
    case: Mapping[str, Any],
    review: Mapping[str, Any],
    reviewed_decisions: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a sealed, reviewed contingency register."""

    validated_case = validate_fdd_case(case)
    artifacts = [dict(item) for item in validated_case["source_artifacts"]]
    decisions = _normalize_reviewed_decisions(reviewed_decisions)
    return validate_contingent_liability_register(
        _seal(
            {
                "schema_version": "vera.contingent_liability_register.v1",
                "register_id": _identifier(register_id, label="register_id"),
                "case": validated_case,
                "case_ref": validated_case["case_id"],
                "scope_id": validated_case["scope_id"],
                "entity_refs": validated_case["entity_refs"],
                "package_ref": validated_case["contract_refs"]["package_ref"],
                "package_sha256": validated_case["contract_refs"]["package_sha256"],
                "currency": validated_case["currency"],
                "unit": validated_case["unit"],
                "reporting_period": validated_case["reporting_period"],
                "source_artifacts": artifacts,
                "review": _normalize_review(review),
                "reviewed_decisions": decisions,
                "completeness": {
                    "status": "not_assessed",
                    "boundary": (
                        "Register validation does not establish that all "
                        "contingent liabilities have been identified."
                    ),
                },
                "items": _normalize_contingency_items(
                    items,
                    available_refs={item["artifact_ref"] for item in artifacts},
                    decision_refs={item["decision_ref"] for item in decisions},
                ),
                "limitations": _text_list(limitations, label="limitations"),
                "report_ready": False,
            }
        )
    )


def _normalize_issue_items(
    value: object,
    *,
    available_refs: set[str],
    decision_refs: set[str],
    metric_receipts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issues = []
    for index, raw_issue in enumerate(_sequence(value, label="issues")):
        label = f"issues[{index}]"
        issue = _mapping(raw_issue, label=label)
        _exact_fields(
            issue,
            required={
                "decision_refs",
                "description",
                "economic_effect_id",
                "evidence_refs",
                "impact",
                "issue_id",
                "open_questions",
                "owner_ref",
                "related_metric_refs",
                "related_pack_refs",
                "status_id",
                "title",
            },
            label=label,
        )
        related_pack_refs = sorted(
            _identifier_list(
                issue["related_pack_refs"],
                label=f"{label}.related_pack_refs",
                allow_empty=True,
            )
        )
        unsupported_packs = sorted(set(related_pack_refs) - set(FDD_PACK_RECIPES))
        if unsupported_packs:
            raise FDDContractError(
                f"{label}.related_pack_refs are unsupported: {unsupported_packs}"
            )
        related_metric_refs = sorted(
            _identifier_list(
                issue["related_metric_refs"],
                label=f"{label}.related_metric_refs",
                allow_empty=True,
            )
        )
        missing_metrics = sorted(set(related_metric_refs) - set(metric_receipts))
        if missing_metrics:
            raise FDDContractError(
                f"{label}.related_metric_refs are unknown: {missing_metrics}"
            )
        if not related_pack_refs and not related_metric_refs:
            raise FDDContractError(
                f"{label} must reference at least one pack or metric"
            )
        metric_packs = {
            metric_receipts[metric_ref]["pack_id"] for metric_ref in related_metric_refs
        }
        if not metric_packs <= set(related_pack_refs):
            raise FDDContractError(
                f"{label}.related_pack_refs do not cover related metrics"
            )
        closed_decisions = sorted(
            _identifier_list(
                issue["decision_refs"],
                label=f"{label}.decision_refs",
            )
        )
        missing_decisions = sorted(set(closed_decisions) - decision_refs)
        if missing_decisions:
            raise FDDContractError(
                f"{label}.decision_refs are not reviewed: {missing_decisions}"
            )
        issues.append(
            {
                "issue_id": _identifier(issue["issue_id"], label=f"{label}.issue_id"),
                "economic_effect_id": _identifier(
                    issue["economic_effect_id"],
                    label=f"{label}.economic_effect_id",
                ),
                "title": _text(issue["title"], label=f"{label}.title"),
                "description": _text(
                    issue["description"], label=f"{label}.description"
                ),
                "status_id": _identifier(
                    issue["status_id"], label=f"{label}.status_id"
                ),
                "owner_ref": _identifier(
                    issue["owner_ref"], label=f"{label}.owner_ref"
                ),
                "related_pack_refs": related_pack_refs,
                "related_metric_refs": related_metric_refs,
                "impact": _normalize_amount_basis(
                    issue["impact"],
                    label=f"{label}.impact",
                    non_negative=False,
                ),
                "decision_refs": closed_decisions,
                "evidence_refs": _normalize_evidence_refs(
                    issue["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    available_refs=available_refs,
                ),
                "open_questions": _text_list(
                    issue["open_questions"], label=f"{label}.open_questions"
                ),
            }
        )
    issues.sort(key=lambda item: item["issue_id"])
    _unique_rows(issues, "issue_id", label="issues")
    _unique_rows(issues, "economic_effect_id", label="issues")
    return issues


def validate_financial_issue_register(value: object) -> dict[str, Any]:
    """Validate evidence-linked issues without making deal decisions."""

    content = _sealed_content(
        value,
        schema_version="vera.financial_issue_register.v1",
        required={
            "case",
            "case_ref",
            "completeness",
            "currency",
            "entity_refs",
            "issues",
            "limitations",
            "metric_receipts",
            "package_ref",
            "package_sha256",
            "register_id",
            "report_ready",
            "reporting_period",
            "review",
            "reviewed_decisions",
            "scope_id",
            "source_artifacts",
            "unit",
        },
        label="financial issue register",
    )
    if content["report_ready"] is not False:
        raise FDDContractError("financial issue register cannot claim report readiness")
    (
        case,
        artifacts,
        available_refs,
        review,
        decisions,
        decision_refs,
    ) = _normalize_register_header(content)
    metric_receipts = [
        validate_fdd_metric_receipt(item)
        for item in _sequence(content["metric_receipts"], label="metric_receipts")
    ]
    metric_receipts.sort(key=lambda item: item["receipt_id"])
    _unique_rows(metric_receipts, "receipt_id", label="metric_receipts")
    case_ref = case["case_id"]
    scope_id = case["scope_id"]
    entity_refs = case["entity_refs"]
    package_ref = case["contract_refs"]["package_ref"]
    package_sha256 = case["contract_refs"]["package_sha256"]
    currency = case["currency"]
    unit = case["unit"]
    reporting_period = case["reporting_period"]
    for receipt in metric_receipts:
        if receipt["case_ref"] != case_ref:
            raise FDDContractError(
                f"metric receipt {receipt['receipt_id']} belongs to another case"
            )
        receipt_case = receipt["case"]
        if (
            receipt_case["scope_id"] != scope_id
            or receipt_case["entity_refs"] != entity_refs
            or receipt_case["contract_refs"]["package_ref"] != package_ref
            or receipt_case["contract_refs"]["package_sha256"] != package_sha256
            or receipt_case["source_artifacts"] != artifacts
        ):
            raise FDDContractError(
                f"metric receipt {receipt['receipt_id']} belongs to another "
                "case context"
            )
        if receipt["currency"] != currency or receipt["unit"] != unit:
            raise FDDContractError(
                f"metric receipt {receipt['receipt_id']} has a different "
                "currency or unit"
            )
        if receipt["reporting_period"] != reporting_period:
            raise FDDContractError(
                f"metric receipt {receipt['receipt_id']} has a different "
                "reporting period"
            )
    metric_index = {item["receipt_id"]: item for item in metric_receipts}
    issues = _normalize_issue_items(
        content["issues"],
        available_refs=available_refs,
        decision_refs=decision_refs,
        metric_receipts=metric_index,
    )
    normalized = {
        "schema_version": "vera.financial_issue_register.v1",
        "register_id": _identifier(content["register_id"], label="register_id"),
        "case": case,
        "case_ref": case_ref,
        "scope_id": scope_id,
        "entity_refs": entity_refs,
        "package_ref": package_ref,
        "package_sha256": package_sha256,
        "currency": currency,
        "unit": unit,
        "reporting_period": reporting_period,
        "source_artifacts": artifacts,
        "review": review,
        "reviewed_decisions": decisions,
        "completeness": _normalize_register_completeness(
            content["completeness"],
            label="completeness",
        ),
        "metric_receipts": metric_receipts,
        "issues": issues,
        "limitations": _text_list(content["limitations"], label="limitations"),
        "report_ready": False,
    }
    if normalized != content:
        raise FDDContractError("financial issue register is not canonical")
    return _seal(normalized)


def build_financial_issue_register(
    *,
    register_id: str,
    case: Mapping[str, Any],
    review: Mapping[str, Any],
    reviewed_decisions: Sequence[Mapping[str, Any]],
    metric_receipts: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a sealed, reviewed financial issue register."""

    validated_case = validate_fdd_case(case)
    artifacts = [dict(item) for item in validated_case["source_artifacts"]]
    decisions = _normalize_reviewed_decisions(reviewed_decisions)
    receipts = [validate_fdd_metric_receipt(item) for item in metric_receipts]
    receipts.sort(key=lambda item: item["receipt_id"])
    _unique_rows(receipts, "receipt_id", label="metric_receipts")
    receipt_index = {item["receipt_id"]: item for item in receipts}
    return validate_financial_issue_register(
        _seal(
            {
                "schema_version": "vera.financial_issue_register.v1",
                "register_id": _identifier(register_id, label="register_id"),
                "case": validated_case,
                "case_ref": validated_case["case_id"],
                "scope_id": validated_case["scope_id"],
                "entity_refs": validated_case["entity_refs"],
                "package_ref": validated_case["contract_refs"]["package_ref"],
                "package_sha256": validated_case["contract_refs"]["package_sha256"],
                "currency": validated_case["currency"],
                "unit": validated_case["unit"],
                "reporting_period": validated_case["reporting_period"],
                "source_artifacts": artifacts,
                "review": _normalize_review(review),
                "reviewed_decisions": decisions,
                "completeness": {
                    "status": "not_assessed",
                    "boundary": (
                        "Register validation does not establish that all "
                        "financial issues or deal implications have been identified."
                    ),
                },
                "metric_receipts": receipts,
                "issues": _normalize_issue_items(
                    issues,
                    available_refs={item["artifact_ref"] for item in artifacts},
                    decision_refs={item["decision_ref"] for item in decisions},
                    metric_receipts=receipt_index,
                ),
                "limitations": _text_list(limitations, label="limitations"),
                "report_ready": False,
            }
        )
    )
