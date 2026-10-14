"""Apply explicit source-bound fiscal corrections while retaining original extraction.

Exact hashes and declared scalar types are mechanical integrity checks. This
module never selects document meaning, missing values or professional treatment.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from parse_fiscal_forms import FiscalField, _normalize_amount

__all__ = ["field_identity", "apply_field_corrections"]


def field_identity(field: FiscalField) -> str:
    """Identify the complete exact producer field, including its original evidence."""
    value = json.dumps(
        field.as_json(), sort_keys=True, ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_field_corrections(
    fields: Sequence[FiscalField],
    source_texts: Mapping[str, str],
    decisions: Mapping[str, Any],
) -> tuple[list[FiscalField], list[dict[str, Any]]]:
    """Correct only reviewed exact fields; return full before/after provenance."""
    if not isinstance(decisions, Mapping):
        raise ValueError("Fiscal corrections must map exact field hashes to decisions")
    existing = {field_identity(field): field for field in fields}
    if len(existing) != len(fields):
        raise ValueError("Fiscal correction field identity is ambiguous")
    if set(decisions) - set(existing):
        raise ValueError("Fiscal correction refers to an unknown or changed field")
    corrected = []
    records = []
    required = {"source_text_sha256", "value", "basis", "reviewer", "confirmed_by_user"}
    for field in fields:
        reference = field_identity(field)
        if reference not in decisions:
            corrected.append(field)
            continue
        decision = decisions[reference]
        if not isinstance(decision, Mapping) or set(decision) != required:
            raise ValueError("Fiscal correction requires the exact review contract")
        if decision["confirmed_by_user"] is not True:
            raise ValueError("Fiscal correction requires explicit user confirmation")
        for key, limit in (("value", 10000), ("basis", 4000), ("reviewer", 160)):
            if (
                not isinstance(decision[key], str)
                or not decision[key].strip()
                or len(decision[key]) > limit
            ):
                raise ValueError(
                    "Fiscal correction requires a nonempty bounded value, basis and reviewer"
                )
        if field.relative_path not in source_texts:
            raise ValueError("Fiscal correction source text is unavailable")
        source_hash = hashlib.sha256(
            source_texts[field.relative_path].encode("utf-8")
        ).hexdigest()
        if decision["source_text_sha256"] != source_hash:
            raise ValueError("Fiscal correction source text changed")
        value = decision["value"].strip()
        normalized = _normalize_amount(value) if field.value_type == "amount" else value
        if field.value_type == "amount":
            try:
                valid = Decimal(normalized).is_finite()
            except InvalidOperation:
                valid = False
            if not valid:
                raise ValueError("Fiscal correction amount must be a finite number")
        if field.value_type == "integer" and not re.fullmatch(r"[+-]?\d+", value):
            raise ValueError("Fiscal correction requires an integer")
        updated = replace(field, value=value, normalized_value=normalized)
        corrected.append(updated)
        records.append(
            {
                "original_field_sha256": reference,
                "corrected_field_sha256": field_identity(updated),
                "original": field.as_json(),
                "corrected": updated.as_json(),
                "review": dict(decision),
            }
        )
    if len({field_identity(field) for field in corrected}) != len(corrected):
        raise ValueError("Fiscal correction would create ambiguous field identities")
    return corrected, records
