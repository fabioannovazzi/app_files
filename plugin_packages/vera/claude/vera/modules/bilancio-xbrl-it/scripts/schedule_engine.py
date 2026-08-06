#!/usr/bin/env python3
"""Exact movement-schedule and indirect cash-flow validation.

These rules are deterministic only for explicit arithmetic identities and
evidence-presence contracts. Schedule applicability, classification, and the
economic nature of movements must be supplied by a reviewer or an accepted
upstream decision; this module never infers them from account text.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

__all__ = [
    "SCHEDULE_TYPES",
    "normalize_schedule",
    "required_schedule_types",
    "schedule_adapter_records",
    "schedule_fact_records",
    "schedule_template_fields",
    "schedule_template_text_fields",
]

SCHEDULE_TYPES = {
    "FIXED_ASSETS",
    "RECEIVABLES",
    "PAYABLES",
    "EQUITY",
    "PROVISIONS",
    "TFR",
    "TAXES",
    "GUARANTEES_COMMITMENTS",
    "CASH_FLOW",
}
EVIDENCE_STATUSES = {"OBSERVED", "USER_CONFIRMED"}
DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

FIXED_ASSET_FIELDS = (
    "opening_gross_cost",
    "opening_revaluations",
    "opening_accumulated_amortisation",
    "opening_accumulated_impairment",
    "opening_net_carrying_amount",
    "additions",
    "capitalised_internal_costs",
    "reclassifications_in",
    "reclassifications_out",
    "disposals_gross_cost",
    "disposals_accumulated_amortisation",
    "disposals_accumulated_impairment",
    "current_revaluations",
    "current_amortisation",
    "current_impairment",
    "impairment_reversals",
    "other_movements",
    "closing_gross_cost",
    "closing_accumulated_amortisation",
    "closing_accumulated_impairment",
    "closing_net_carrying_amount",
)
MATURITY_FIELDS = (
    "opening_amount",
    "increases",
    "decreases",
    "reclassifications",
    "exchange_effects",
    "other_movements",
    "closing_amount",
    "due_within_next_year",
    "due_after_next_year",
    "over_five_years",
)
PAYABLE_FIELDS = (*MATURITY_FIELDS, "secured_amount")
RECEIVABLE_ALLOWANCE_FIELDS = (
    "gross_closing_amount",
    "allowance_opening",
    "allowance_additions",
    "allowance_uses",
    "allowance_releases",
    "allowance_other_movements",
    "allowance_closing",
)
MOVEMENT_FIELDS = (
    "opening_amount",
    "additions",
    "uses",
    "releases",
    "other_increases",
    "other_decreases",
    "closing_amount",
)
EQUITY_FIELDS = (
    "opening_amount",
    "prior_result_allocation",
    "contributions",
    "reductions",
    "dividends",
    "transfers_in",
    "transfers_out",
    "reserve_uses",
    "current_year_result",
    "other_movements",
    "closing_amount",
)
TAX_FIELDS = (
    "opening_amount",
    "increases",
    "decreases",
    "closing_amount",
    "current_tax_expense",
    "tax_base",
    "temporary_difference",
    "recognised_amount",
    "unrecognised_amount",
)
SCHEDULE_TEXT_FIELDS = {
    "FIXED_ASSETS": ("asset_class", "ownership_status", "pledged_status"),
    "RECEIVABLES": (
        "receivable_class",
        "geography",
        "related_party_class",
        "factoring_status",
        "measurement_basis",
        "currency",
        "tax_class",
    ),
    "PAYABLES": (
        "payable_class",
        "geography",
        "related_party_class",
        "security_type",
        "guarantee_asset",
        "covenant_status",
        "shareholder_financing_status",
        "currency",
    ),
    "EQUITY": (
        "equity_class",
        "origin",
        "availability",
        "distributability",
        "prior_uses",
        "treasury_shares_status",
        "fair_value_reserve_status",
    ),
    "PROVISIONS": ("provision_class",),
    "TFR": ("tfr_class",),
    "TAXES": ("tax_type", "jurisdiction", "recoverability_assessment"),
    "GUARANTEES_COMMITMENTS": (
        "guarantee_type",
        "beneficiary",
        "secured_asset",
        "related_party_class",
        "expiry",
    ),
}


def schedule_template_fields(schedule_type: str) -> tuple[str, ...]:
    """Return exact required columns for a normalized supporting-file template."""

    normalized = schedule_type.upper()
    if normalized == "FIXED_ASSETS":
        return FIXED_ASSET_FIELDS
    if normalized == "RECEIVABLES":
        return (*MATURITY_FIELDS, *RECEIVABLE_ALLOWANCE_FIELDS)
    if normalized == "PAYABLES":
        return PAYABLE_FIELDS
    if normalized == "EQUITY":
        return EQUITY_FIELDS
    if normalized in {"PROVISIONS", "TFR"}:
        return MOVEMENT_FIELDS
    if normalized == "TAXES":
        return TAX_FIELDS
    if normalized == "GUARANTEES_COMMITMENTS":
        return ("closing_amount",)
    raise ValueError(f"No row template exists for schedule type: {normalized}")


def schedule_template_text_fields(schedule_type: str) -> tuple[str, ...]:
    """Return semantic fields that must be supplied or explicitly remain unknown."""

    normalized = schedule_type.upper()
    if normalized not in SCHEDULE_TEXT_FIELDS:
        raise ValueError(f"No semantic template exists for schedule type: {normalized}")
    return SCHEDULE_TEXT_FIELDS[normalized]


def schedule_fact_records(schedule: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose stable monetary fact references from one normalized schedule."""

    schedule_id = str(schedule["schedule_id"])
    schedule_type = str(schedule["schedule_type"]).upper()
    records: list[dict[str, Any]] = []
    if schedule_type == "CASH_FLOW":
        common_refs = sorted(
            {
                str(ref)
                for item in schedule.get("items", [])
                for ref in item.get("source_refs", [])
            }
        )
        cash_values = {
            "opening_cash": str(schedule["opening_cash"]),
            "closing_cash": str(schedule["closing_cash"]),
            "net_change": _text(
                _decimal(schedule["closing_cash"], "closing_cash")
                - _decimal(schedule["opening_cash"], "opening_cash")
            ),
        }
        for field, value in cash_values.items():
            records.append(
                {
                    "fact_id": f"schedule:{schedule_id}:cash:{field}",
                    "schedule_id": schedule_id,
                    "row_id": "cash",
                    "key": field,
                    "value": value,
                    "source_refs": common_refs,
                }
            )
        for item in schedule.get("items", []):
            records.append(
                {
                    "fact_id": (f"schedule:{schedule_id}:{item['item_id']}:amount"),
                    "schedule_id": schedule_id,
                    "row_id": str(item["item_id"]),
                    "key": "amount",
                    "value": str(item["amount"]),
                    "source_refs": list(item.get("source_refs", [])),
                }
            )
        return records
    fields = schedule_template_fields(schedule_type)
    for row in schedule.get("rows", []):
        row_id = str(row["row_id"])
        for field in fields:
            records.append(
                {
                    "fact_id": f"schedule:{schedule_id}:{row_id}:{field}",
                    "schedule_id": schedule_id,
                    "row_id": row_id,
                    "key": field,
                    "value": str(row[field]),
                    "source_refs": list(row.get("source_refs", [])),
                }
            )
    return records


def schedule_adapter_records(schedule: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose every reviewed schedule cell to the taxonomy adapter.

    Monetary and semantic text cells use stable identifiers.  The adapter can
    therefore prove that each cell was mapped to an official concept or was
    explicitly omitted by the professional, without interpreting free-form
    row labels or inventing a taxonomy classification.
    """

    records = [
        {**item, "fact_type": "MONETARY"} for item in schedule_fact_records(schedule)
    ]
    schedule_type = str(schedule["schedule_type"]).upper()
    if schedule_type == "CASH_FLOW":
        return records
    schedule_id = str(schedule["schedule_id"])
    for row in schedule.get("rows", []):
        row_id = str(row["row_id"])
        for field in schedule_template_text_fields(schedule_type):
            records.append(
                {
                    "fact_id": f"schedule:{schedule_id}:{row_id}:{field}",
                    "schedule_id": schedule_id,
                    "row_id": row_id,
                    "key": field,
                    "value": str(row[field]),
                    "source_refs": list(row.get("source_refs", [])),
                    "fact_type": "TEXT",
                }
            )
    return records


def _decimal(value: Any, field: str) -> Decimal:
    text = str(value)
    if not DECIMAL_PATTERN.fullmatch(text):
        raise ValueError(f"Schedule field {field} must be a normalized decimal string")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Schedule field {field} is invalid") from exc


def _text(value: Decimal) -> str:
    return format(value, "f")


def _statement_amount(
    statement_facts: Sequence[Mapping[str, Any]], canonical_line: str, period: str
) -> Decimal:
    key = "current_value" if period == "CURRENT" else "prior_value"
    matches = [
        _decimal(fact[key], key)
        for fact in statement_facts
        if fact.get("canonical_line", fact.get("key")) == canonical_line
    ]
    if not matches:
        raise ValueError(f"Schedule statement line is absent: {canonical_line}")
    return sum(matches, Decimal("0"))


def _normalize_row(
    row: Mapping[str, Any],
    fields: Sequence[str],
    schedule_type: str,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    source_refs = sorted(
        {str(value) for value in row.get("source_refs", []) if str(value)}
    )
    status = str(row.get("evidence_status", "")).upper()
    if not source_refs or status not in EVIDENCE_STATUSES:
        raise ValueError(
            f"{schedule_type} rows require source refs and observed or user-confirmed evidence"
        )
    normalized: dict[str, Any] = {
        "row_id": str(row["row_id"]),
        "label": str(row.get("label", row["row_id"])),
        "source_refs": source_refs,
        "evidence_status": status,
    }
    for field in fields:
        normalized[field] = _text(_decimal(row[field], field))
    for field in schedule_template_text_fields(schedule_type):
        value = str(row.get(field, "")).strip()
        if not value or value.upper() == "UNKNOWN":
            normalized[field] = "UNKNOWN"
            issues.append(
                {
                    "rule_id": f"SCHEDULE.{schedule_type}.{field.upper()}_REQUIRED",
                    "row_id": normalized["row_id"],
                    "field": field,
                }
            )
        else:
            normalized[field] = value
    return normalized


def _fixed_assets(
    rows: Sequence[Mapping[str, Any]], issues: list[dict[str, str]]
) -> list[dict[str, Any]]:
    normalized = [
        _normalize_row(row, FIXED_ASSET_FIELDS, "FIXED_ASSETS", issues) for row in rows
    ]
    for row in normalized:
        value = lambda field: _decimal(row[field], field)
        opening_net = (
            value("opening_gross_cost")
            + value("opening_revaluations")
            - value("opening_accumulated_amortisation")
            - value("opening_accumulated_impairment")
        )
        closing_net = (
            value("closing_gross_cost")
            - value("closing_accumulated_amortisation")
            - value("closing_accumulated_impairment")
        )
        net_disposals = (
            value("disposals_gross_cost")
            - value("disposals_accumulated_amortisation")
            - value("disposals_accumulated_impairment")
        )
        movement_close = (
            value("opening_net_carrying_amount")
            + value("additions")
            + value("capitalised_internal_costs")
            + value("reclassifications_in")
            - value("reclassifications_out")
            - net_disposals
            + value("current_revaluations")
            - value("current_amortisation")
            - value("current_impairment")
            + value("impairment_reversals")
            + value("other_movements")
        )
        if opening_net != value("opening_net_carrying_amount"):
            issues.append(
                {"rule_id": "SCHEDULE.FIXED_ASSET_OPENING", "row_id": row["row_id"]}
            )
        if closing_net != value("closing_net_carrying_amount"):
            issues.append(
                {"rule_id": "SCHEDULE.FIXED_ASSET_CLOSING", "row_id": row["row_id"]}
            )
        if movement_close != value("closing_net_carrying_amount"):
            issues.append(
                {"rule_id": "SCHEDULE.FIXED_ASSET_MOVEMENT", "row_id": row["row_id"]}
            )
    reclassifications = sum(
        _decimal(row["reclassifications_in"], "reclassifications_in")
        - _decimal(row["reclassifications_out"], "reclassifications_out")
        for row in normalized
    )
    if reclassifications != 0:
        issues.append({"rule_id": "SCHEDULE.RECLASSIFICATIONS_NET_ZERO", "row_id": "*"})
    return normalized


def _maturity(
    rows: Sequence[Mapping[str, Any]], schedule_type: str, issues: list[dict[str, str]]
) -> list[dict[str, Any]]:
    fields = (
        (*MATURITY_FIELDS, *RECEIVABLE_ALLOWANCE_FIELDS)
        if schedule_type == "RECEIVABLES"
        else PAYABLE_FIELDS
    )
    normalized = [_normalize_row(row, fields, schedule_type, issues) for row in rows]
    for row in normalized:
        value = lambda field: _decimal(row[field], field)
        if any(
            value(field) < 0
            for field in (
                "closing_amount",
                "due_within_next_year",
                "due_after_next_year",
                "over_five_years",
            )
        ):
            raise ValueError(f"{schedule_type} maturity amounts must not be negative")
        movement_close = (
            value("opening_amount")
            + value("increases")
            - value("decreases")
            + value("reclassifications")
            + value("exchange_effects")
            + value("other_movements")
        )
        if movement_close != value("closing_amount"):
            issues.append(
                {
                    "rule_id": f"SCHEDULE.{schedule_type}_MOVEMENT",
                    "row_id": row["row_id"],
                }
            )
        if value("due_within_next_year") + value("due_after_next_year") != value(
            "closing_amount"
        ):
            issues.append(
                {
                    "rule_id": f"SCHEDULE.{schedule_type}_MATURITY",
                    "row_id": row["row_id"],
                }
            )
        if value("over_five_years") < 0 or value("over_five_years") > value(
            "due_after_next_year"
        ):
            issues.append(
                {
                    "rule_id": f"SCHEDULE.{schedule_type}_OVER_FIVE",
                    "row_id": row["row_id"],
                }
            )
        if schedule_type == "PAYABLES" and (
            value("secured_amount") < 0
            or value("secured_amount") > value("closing_amount")
        ):
            issues.append(
                {
                    "rule_id": "SCHEDULE.PAYABLES_SECURED_AMOUNT",
                    "row_id": row["row_id"],
                }
            )
        if schedule_type == "RECEIVABLES":
            allowance_close = (
                value("allowance_opening")
                + value("allowance_additions")
                - value("allowance_uses")
                - value("allowance_releases")
                + value("allowance_other_movements")
            )
            if allowance_close != value("allowance_closing"):
                issues.append(
                    {
                        "rule_id": "SCHEDULE.RECEIVABLES_ALLOWANCE_MOVEMENT",
                        "row_id": row["row_id"],
                    }
                )
            if value("gross_closing_amount") - value("allowance_closing") != value(
                "closing_amount"
            ):
                issues.append(
                    {
                        "rule_id": "SCHEDULE.RECEIVABLES_NET_BALANCE",
                        "row_id": row["row_id"],
                    }
                )
    return normalized


def _movement(
    rows: Sequence[Mapping[str, Any]], schedule_type: str, issues: list[dict[str, str]]
) -> list[dict[str, Any]]:
    fields = EQUITY_FIELDS if schedule_type == "EQUITY" else MOVEMENT_FIELDS
    normalized = [_normalize_row(row, fields, schedule_type, issues) for row in rows]
    for row in normalized:
        value = lambda field: _decimal(row[field], field)
        if schedule_type == "EQUITY":
            calculated = (
                value("opening_amount")
                + value("prior_result_allocation")
                + value("contributions")
                - value("reductions")
                - value("dividends")
                + value("transfers_in")
                - value("transfers_out")
                - value("reserve_uses")
                + value("current_year_result")
                + value("other_movements")
            )
        else:
            calculated = (
                value("opening_amount")
                + value("additions")
                - value("uses")
                - value("releases")
                + value("other_increases")
                - value("other_decreases")
            )
        if calculated != value("closing_amount"):
            issues.append(
                {
                    "rule_id": f"SCHEDULE.{schedule_type}_MOVEMENT",
                    "row_id": row["row_id"],
                }
            )
    return normalized


def _cash_flow(
    payload: Mapping[str, Any],
    statement_facts: Sequence[Mapping[str, Any]],
    issues: list[dict[str, str]],
    comparative_required: bool,
) -> dict[str, Any]:
    cash_line = str(payload["cash_statement_line"])
    opening = _decimal(payload["opening_cash"], "opening_cash")
    closing = _decimal(payload["closing_cash"], "closing_cash")
    if comparative_required and opening != _statement_amount(
        statement_facts, cash_line, "PRIOR"
    ):
        issues.append({"rule_id": "CASH_FLOW.OPENING_CASH", "row_id": "cash"})
    if closing != _statement_amount(statement_facts, cash_line, "CURRENT"):
        issues.append({"rule_id": "CASH_FLOW.CLOSING_CASH", "row_id": "cash"})
    items: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        category = str(item["category"]).upper()
        if category not in {"OPERATING", "INVESTING", "FINANCING"}:
            raise ValueError(
                "Cash-flow category must be operating, investing, or financing"
            )
        source_refs = sorted(
            {str(value) for value in item.get("source_refs", []) if str(value)}
        )
        status = str(item.get("evidence_status", "")).upper()
        evidence_type = str(item.get("movement_evidence_type", "")).upper()
        if not source_refs or status not in EVIDENCE_STATUSES:
            raise ValueError("Every cash-flow item requires accepted movement evidence")
        if evidence_type not in {"SCHEDULE", "LEDGER_DETAIL", "USER_ADJUSTMENT"}:
            raise ValueError("Cash-flow movement evidence type is not supported")
        items.append(
            {
                "item_id": str(item["item_id"]),
                "category": category,
                "amount": _text(_decimal(item["amount"], "amount")),
                "source_refs": source_refs,
                "evidence_status": status,
                "movement_evidence_type": evidence_type,
                "rationale": str(item.get("rationale", "")),
            }
        )
    item_ids = [item["item_id"] for item in items]
    if not item_ids or "" in item_ids or len(item_ids) != len(set(item_ids)):
        raise ValueError("Cash-flow item IDs must be present and unique")
    if (
        sum((_decimal(item["amount"], "amount") for item in items), Decimal("0"))
        != closing - opening
    ):
        issues.append({"rule_id": "CASH_FLOW.NET_CHANGE", "row_id": "cash"})
    return {
        "cash_statement_line": cash_line,
        "opening_cash": _text(opening),
        "closing_cash": _text(closing),
        "items": items,
    }


def normalize_schedule(
    payload: Mapping[str, Any],
    statement_facts: Sequence[Mapping[str, Any]],
    *,
    comparative_required: bool = True,
) -> dict[str, Any]:
    """Normalize one explicit schedule and return its arithmetic issues."""

    schedule_type = str(payload["schedule_type"]).upper()
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(f"Unsupported schedule type: {schedule_type}")
    issues: list[dict[str, str]] = []
    if schedule_type == "CASH_FLOW":
        content = _cash_flow(payload, statement_facts, issues, comparative_required)
        statement_line = content["cash_statement_line"]
    else:
        rows = list(payload.get("rows", []))
        if not rows:
            raise ValueError(f"{schedule_type} requires at least one row")
        row_ids = [str(row.get("row_id", "")) for row in rows]
        if "" in row_ids or len(row_ids) != len(set(row_ids)):
            raise ValueError(f"{schedule_type} row IDs must be present and unique")
        statement_multiplier = _decimal(
            payload.get("statement_multiplier", "1"), "statement_multiplier"
        )
        if statement_multiplier not in {Decimal("-1"), Decimal("1")}:
            raise ValueError("Schedule statement multiplier must be 1 or -1")
        statement_line = (
            None
            if schedule_type == "GUARANTEES_COMMITMENTS"
            else str(payload["statement_line"])
        )
        if schedule_type == "FIXED_ASSETS":
            normalized_rows = _fixed_assets(rows, issues)
            closing_field = "closing_net_carrying_amount"
            opening_field = "opening_net_carrying_amount"
            amortisation_line = payload.get("amortisation_statement_line")
            amortisation_exception = payload.get(
                "amortisation_reconciliation_exception"
            )
            if amortisation_line:
                amortisation_multiplier = _decimal(
                    payload.get("amortisation_statement_multiplier", "1"),
                    "amortisation_statement_multiplier",
                )
                if amortisation_multiplier not in {Decimal("-1"), Decimal("1")}:
                    raise ValueError(
                        "Amortisation statement multiplier must be 1 or -1"
                    )
                amortisation_total = sum(
                    (
                        _decimal(row["current_amortisation"], "current_amortisation")
                        for row in normalized_rows
                    ),
                    Decimal("0"),
                )
                if amortisation_total * amortisation_multiplier != _statement_amount(
                    statement_facts, str(amortisation_line), "CURRENT"
                ):
                    issues.append(
                        {
                            "rule_id": "SCHEDULE.FIXED_ASSET_AMORTISATION",
                            "row_id": "*",
                        }
                    )
            elif not (
                isinstance(amortisation_exception, Mapping)
                and str(amortisation_exception.get("reason", "")).strip()
                and amortisation_exception.get("source_refs")
            ):
                issues.append(
                    {
                        "rule_id": "SCHEDULE.FIXED_ASSET_AMORTISATION_EVIDENCE",
                        "row_id": "*",
                    }
                )
        elif schedule_type in {"RECEIVABLES", "PAYABLES"}:
            normalized_rows = _maturity(rows, schedule_type, issues)
            closing_field = "closing_amount"
            opening_field = "opening_amount"
        elif schedule_type in {"EQUITY", "PROVISIONS", "TFR"}:
            normalized_rows = _movement(rows, schedule_type, issues)
            closing_field = "closing_amount"
            opening_field = "opening_amount"
        elif schedule_type == "TAXES":
            normalized_rows = [
                _normalize_row(row, TAX_FIELDS, schedule_type, issues) for row in rows
            ]
            closing_field = "closing_amount"
            opening_field = "opening_amount"
            for row in normalized_rows:
                if _decimal(row["opening_amount"], "opening_amount") + _decimal(
                    row["increases"], "increases"
                ) - _decimal(row["decreases"], "decreases") != _decimal(
                    row["closing_amount"], "closing_amount"
                ):
                    issues.append(
                        {
                            "rule_id": "SCHEDULE.TAXES_MOVEMENT",
                            "row_id": row["row_id"],
                        }
                    )
        elif schedule_type == "GUARANTEES_COMMITMENTS":
            normalized_rows = [
                _normalize_row(row, ("closing_amount",), schedule_type, issues)
                for row in rows
            ]
            closing_field = "closing_amount"
            opening_field = None
        else:
            raise AssertionError(schedule_type)
        schedule_total = sum(
            (_decimal(row[closing_field], closing_field) for row in normalized_rows),
            Decimal("0"),
        )
        if schedule_type != "GUARANTEES_COMMITMENTS":
            if statement_line is None:
                raise ValueError("This schedule requires a statement line")
            statement_total = _statement_amount(
                statement_facts, statement_line, "CURRENT"
            )
            if schedule_total * statement_multiplier != statement_total:
                issues.append(
                    {
                        "rule_id": "SCHEDULE.STATEMENT_RECONCILIATION",
                        "row_id": "*",
                    }
                )
        if opening_field is not None and comparative_required:
            opening_total = sum(
                (
                    _decimal(row[opening_field], opening_field)
                    for row in normalized_rows
                ),
                Decimal("0"),
            )
            prior_statement_total = _statement_amount(
                statement_facts, statement_line, "PRIOR"
            )
            if opening_total * statement_multiplier != prior_statement_total:
                issues.append(
                    {
                        "rule_id": "SCHEDULE.PRIOR_STATEMENT_RECONCILIATION",
                        "row_id": "*",
                    }
                )
        content = {
            "statement_line": statement_line,
            "statement_multiplier": _text(statement_multiplier),
            "rows": normalized_rows,
        }
        if schedule_type == "FIXED_ASSETS":
            content["amortisation_statement_line"] = payload.get(
                "amortisation_statement_line"
            )
            content["amortisation_reconciliation_exception"] = payload.get(
                "amortisation_reconciliation_exception"
            )
    return {
        "schedule_id": str(payload["schedule_id"]),
        "schedule_type": schedule_type,
        **content,
        "status": "COMPLETE" if not issues else "INCOMPLETE",
        "comparative_reconciliation": (
            "PERFORMED"
            if comparative_required
            else "NOT_APPLICABLE_FIRST_FINANCIAL_YEAR"
        ),
        "issues": issues,
    }


def required_schedule_types(case: Mapping[str, Any]) -> set[str]:
    """Return evidence-derived/reviewer triggers plus mandatory ordinary cash flow."""

    required = {
        str(trigger).upper()
        for mapping in case.get("mappings", [])
        for allocation in mapping.get("allocations", [])
        for trigger in allocation.get("schedule_triggers", [])
    }
    required.update(
        str(item["schedule_type"]).upper()
        for item in (case.get("statutory_presentation") or {}).get(
            "derived_schedule_triggers", []
        )
    )
    if case.get("selected_form") == "ORDINARY":
        required.add("CASH_FLOW")
    unknown = required - SCHEDULE_TYPES
    if unknown:
        raise ValueError(f"Unknown schedule triggers: {sorted(unknown)}")
    return required
