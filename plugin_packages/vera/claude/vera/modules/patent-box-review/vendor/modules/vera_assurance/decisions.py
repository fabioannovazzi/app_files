"""Reviewed-decision receipts bound to exact source and adapter identities."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from .serialization import canonical_json_sha256

__all__ = [
    "DecisionReceiptError",
    "build_reviewed_decision_receipt",
    "validate_reviewed_decision_receipt",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_STATUSES = {"draft", "reviewed", "rejected", "superseded"}


class DecisionReceiptError(ValueError):
    """Raised when a decision receipt is invalid or stale."""


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DecisionReceiptError(f"{label} must be non-empty trimmed text")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise DecisionReceiptError(f"{label} must be a canonical identifier")
    return text


def _source_refs(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DecisionReceiptError("source_artifact_refs must be a list")
    refs = [
        _identifier(item, label=f"source_artifact_refs[{index}]")
        for index, item in enumerate(value)
    ]
    if not refs or len(refs) != len(set(refs)):
        raise DecisionReceiptError("source_artifact_refs must be non-empty and unique")
    return refs


def validate_reviewed_decision_receipt(
    value: object,
    *,
    expected_decision_id: str | None = None,
    expected_decision_type: str | None = None,
    expected_source_artifact_refs: Sequence[str] | None = None,
    expected_adapter_id: str | None = None,
    expected_adapter_version: str | None = None,
    require_reviewed: bool = False,
) -> dict[str, Any]:
    """Validate a decision receipt and optional current-source bindings."""

    if not isinstance(value, Mapping):
        raise DecisionReceiptError("decision receipt must be an object")
    required = {
        "schema_version",
        "decision_id",
        "decision_type",
        "status",
        "reviewer_ref",
        "reviewed_on",
        "adapter_id",
        "adapter_version",
        "source_artifact_refs",
        "content",
        "content_sha256",
    }
    missing = required - set(value)
    unexpected = set(value) - required
    if missing or unexpected:
        raise DecisionReceiptError(
            f"decision receipt fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    if value["schema_version"] != "vera.reviewed_decision_receipt.v1":
        raise DecisionReceiptError("unsupported decision receipt schema")
    status = _text(value["status"], label="status")
    if status not in _STATUSES:
        raise DecisionReceiptError("unsupported decision status")
    if require_reviewed and status != "reviewed":
        raise DecisionReceiptError("decision must have reviewed status")
    reviewed_on = _text(value["reviewed_on"], label="reviewed_on")
    try:
        date.fromisoformat(reviewed_on)
    except ValueError as exc:
        raise DecisionReceiptError("reviewed_on must be an ISO date") from exc
    adapter_id = _identifier(value["adapter_id"], label="adapter_id")
    adapter_version = _identifier(value["adapter_version"], label="adapter_version")
    source_refs = _source_refs(value["source_artifact_refs"])
    if not isinstance(value["content"], Mapping):
        raise DecisionReceiptError("content must be an object")
    content = dict(value["content"])
    expected_digest = canonical_json_sha256(content)
    if value["content_sha256"] != expected_digest:
        raise DecisionReceiptError("decision content digest is stale")
    if expected_source_artifact_refs is not None:
        current_refs = _source_refs(list(expected_source_artifact_refs))
        if source_refs != current_refs:
            raise DecisionReceiptError("decision source binding is stale")
    if expected_adapter_id is not None and adapter_id != expected_adapter_id:
        raise DecisionReceiptError("decision adapter binding is stale")
    if (
        expected_adapter_version is not None
        and adapter_version != expected_adapter_version
    ):
        raise DecisionReceiptError("decision adapter version is stale")
    normalized = {
        "schema_version": "vera.reviewed_decision_receipt.v1",
        "decision_id": _identifier(value["decision_id"], label="decision_id"),
        "decision_type": _identifier(value["decision_type"], label="decision_type"),
        "status": status,
        "reviewer_ref": _identifier(value["reviewer_ref"], label="reviewer_ref"),
        "reviewed_on": reviewed_on,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "source_artifact_refs": source_refs,
        "content": content,
        "content_sha256": expected_digest,
    }
    if expected_decision_id is not None and normalized["decision_id"] != _identifier(
        expected_decision_id, label="expected_decision_id"
    ):
        raise DecisionReceiptError("decision identity is stale")
    if expected_decision_type is not None and normalized[
        "decision_type"
    ] != _identifier(expected_decision_type, label="expected_decision_type"):
        raise DecisionReceiptError("decision type is stale")
    return normalized


def build_reviewed_decision_receipt(
    *,
    decision_id: str,
    decision_type: str,
    status: str,
    reviewer_ref: str,
    reviewed_on: str,
    adapter_id: str,
    adapter_version: str,
    source_artifact_refs: Sequence[str],
    content: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and seal a reviewed-decision receipt."""

    payload = {
        "schema_version": "vera.reviewed_decision_receipt.v1",
        "decision_id": decision_id,
        "decision_type": decision_type,
        "status": status,
        "reviewer_ref": reviewer_ref,
        "reviewed_on": reviewed_on,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "source_artifact_refs": list(source_artifact_refs),
        "content": dict(content),
        "content_sha256": canonical_json_sha256(content),
    }
    return validate_reviewed_decision_receipt(payload)
