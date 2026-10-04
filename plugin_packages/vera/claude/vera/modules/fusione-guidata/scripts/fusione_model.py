"""Structural contracts for the merger foundation; no legal classification."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

__all__ = ["CaseError", "canonical", "digest", "identifier", "validate_data"]

KINDS = {
    "Operation",
    "Entity",
    "OwnershipEdge",
    "Evidence",
    "Fact",
    "SourceVersion",
    "RuleVersion",
    "BranchDecision",
    "Decision",
    "ChangeImpact",
    "Artifact",
    "Valuation",
    "ExchangeModel",
    "BookBridge",
    "Deadline",
    "LegalDocument",
    "ArchiveBinding",
}
WORK_STATES = {
    "draft",
    "in_progress",
    "missing_evidence",
    "review_pending",
    "not_applicable",
}


class CaseError(ValueError):
    """A structural, provenance, access or revision precondition was not met."""


def canonical(value: Any) -> bytes:
    """Use one exact JSON representation for content and approval fingerprints."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_-]{0,79}", value
    ):
        raise CaseError(
            "Use an identifier starting with a letter, with letters, digits, _ or -."
        )
    return value


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaseError(f"{label} must be non-empty text.")
    return value


def iso_date(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CaseError("Dates must be ISO YYYY-MM-DD strings.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise CaseError("Invalid calendar date.") from exc


def decimal_string(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        raise CaseError("Amounts must be decimal strings, never floats.")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise CaseError("Invalid decimal amount.") from exc
    return number


def fraction_string(value: Any) -> Fraction:
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+/[1-9]\d*", value):
        raise CaseError("Ratios must be explicit numerator/denominator strings.")
    return Fraction(value)


def no_floats(value: Any) -> None:
    if isinstance(value, float):
        raise CaseError("Floating point values are not accepted in case records.")
    if isinstance(value, dict):
        for nested in value.values():
            no_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            no_floats(nested)


def validate_data(kind: str, data: dict[str, Any]) -> None:
    """Check shapes and exact types; this never approves meaning or applicability."""
    if kind not in KINDS or not isinstance(data, dict):
        raise CaseError("Unknown record kind or non-object data.")
    no_floats(data)
    if kind in {
        "Valuation",
        "ExchangeModel",
        "BookBridge",
        "Deadline",
        "LegalDocument",
    } or (kind == "BranchDecision" and "engine_version" in data):
        if (
            set(data) != {"engine_version", "request", "result", "issues"}
            or data["engine_version"] != "fusione.p1.v1"
        ):
            raise CaseError("Invalid P1 workpaper envelope.")
        if not isinstance(data["request"], dict) or not isinstance(
            data["issues"], list
        ):
            raise CaseError("P1 request and issues must remain explicit.")
        if data["result"] is not None and not isinstance(data["result"], dict):
            raise CaseError("Invalid P1 result.")
        for issue in data["issues"]:
            text(issue, "workpaper issue")
        return
    if kind == "ArchiveBinding":
        required_binding = {
            "entity_id",
            "client_root",
            "client_id",
            "engagement_id",
            "client_sha256",
            "engagement_sha256",
        }
        if set(data) != required_binding:
            raise CaseError("Invalid Studio Archive binding.")
        for key in required_binding:
            text(data[key], key)
        return
    required = {
        "Operation": {
            "operation_type",
            "objectives",
            "jurisdictions",
            "planned_date",
            "actual_date",
        },
        "Entity": {
            "name",
            "legal_form",
            "role",
            "residence",
            "accounting_framework",
            "source_roots",
        },
        "OwnershipEdge": {"holder", "company", "ratio", "rights", "as_of"},
        "Fact": {"description", "fact_status", "value_kind", "value", "unit", "as_of"},
        "SourceVersion": {
            "title",
            "url",
            "checked_on",
            "access_status",
            "error",
            "source_version",
        },
        "RuleVersion": {
            "statement",
            "citation",
            "review_status",
            "published_on",
            "effective_from",
            "effective_to",
            "applicable_from",
            "applicable_to",
            "transitional_notes",
            "scope",
            "preconditions",
            "exceptions",
            "test_refs",
        },
        "BranchDecision": {"branch", "rationale", "conditions", "support_status"},
    }
    fields = required.get(kind)
    if fields is not None and set(data) != fields:
        raise CaseError(f"{kind} requires exactly these fields: {sorted(fields)}")
    if kind == "Operation":
        if data["operation_type"] != "fusione":
            raise CaseError("This case must explicitly identify a fusione operation.")
        text(data["objectives"], "objectives")
        if not isinstance(data["jurisdictions"], list) or not data["jurisdictions"]:
            raise CaseError("Record the operation jurisdictions explicitly.")
        for jurisdiction in data["jurisdictions"]:
            text(jurisdiction, "jurisdiction")
        for field in ("planned_date", "actual_date"):
            if data[field] is not None:
                iso_date(data[field])
    elif kind == "Entity":
        for field in (
            "name",
            "legal_form",
            "role",
            "residence",
            "accounting_framework",
        ):
            text(data[field], field)
        if not isinstance(data["source_roots"], list):
            raise CaseError(
                "source_roots must explicitly list permitted import directories."
            )
    elif kind == "OwnershipEdge":
        identifier(data["holder"])
        identifier(data["company"])
        if not 0 <= fraction_string(data["ratio"]) <= 1:
            raise CaseError("Ownership must be between zero and one.")
        text(data["rights"], "rights")
        iso_date(data["as_of"])
    elif kind == "Fact":
        text(data["description"], "description")
        text(data["unit"], "unit")
        iso_date(data["as_of"])
        state = data["fact_status"]
        if state not in {"known", "unknown", "disputed"}:
            raise CaseError("Fact status must be known, unknown or disputed.")
        if data["value_kind"] not in {"text", "decimal", "fraction", "date", "boolean"}:
            raise CaseError("Unsupported fact value kind.")
        if state != "known":
            if data["value"] is not None:
                raise CaseError(
                    "Unknown and disputed facts retain a null value; record alternatives in evidence."
                )
        elif data["value_kind"] == "decimal":
            decimal_string(data["value"])
        elif data["value_kind"] == "fraction":
            fraction_string(data["value"])
        elif data["value_kind"] == "date":
            iso_date(data["value"])
        elif data["value_kind"] == "boolean":
            if not isinstance(data["value"], bool):
                raise CaseError("A known boolean fact requires true or false.")
        else:
            text(data["value"], "value")
    elif kind == "SourceVersion":
        for field in ("title", "url", "source_version"):
            text(data[field], field)
        if not data["url"].startswith(("https://", "http://")):
            raise CaseError(
                "Record an explicit HTTP(S) source URL; the helper does not fetch it."
            )
        iso_date(data["checked_on"])
        if data["access_status"] not in {"retrieved", "failed", "not_checked"}:
            raise CaseError("Unknown source access status.")
        if data["access_status"] == "failed":
            text(data["error"], "source failure")
        elif data["error"] is not None:
            raise CaseError("Non-failed source attempts must have a null error.")
    elif kind == "RuleVersion":
        for field in ("statement", "citation", "transitional_notes", "scope"):
            text(data[field], field)
        if data["review_status"] not in {
            "candidate",
            "source_checked",
            "professional_review_pending",
            "superseded",
            "withdrawn",
        }:
            raise CaseError(
                "Rule approval is a separate exact-version Decision, never a JSON status."
            )
        for field in (
            "published_on",
            "effective_from",
            "effective_to",
            "applicable_from",
            "applicable_to",
        ):
            if data[field] is not None:
                iso_date(data[field])
        for start, end in (
            ("effective_from", "effective_to"),
            ("applicable_from", "applicable_to"),
        ):
            if data[start] and data[end] and data[start] > data[end]:
                raise CaseError("A temporal interval ends before it begins.")
        for field in ("preconditions", "exceptions", "test_refs"):
            if not isinstance(data[field], list):
                raise CaseError(f"{field} must be an explicit list.")
            for item in data[field]:
                text(item, field)
    elif kind == "BranchDecision":
        for field in ("branch", "rationale", "conditions"):
            text(data[field], field)
        if data["support_status"] != "unsupported":
            raise CaseError(
                "P0 records branch proposals; execution of every legal merger branch is unsupported."
            )
