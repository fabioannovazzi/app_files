#!/usr/bin/env python3
"""Validate evidence-backed case facts and an explicitly authored timeline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from acquisition_binding import AcquisitionBindingError, build_acquisition_binding
from case_core import (
    ensure_safe_output_dir,
    mark_private_file,
    prepare_private_directory,
    read_fragment_text,
    write_json,
)
from privacy_guard import privacy_issue, safe_identifier

__all__ = ["validate_case_records", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FACT_STATUSES = {"confirmed", "disputed", "pending"}
DATE_PRECISIONS = {"day", "month", "year"}
VALUE_TYPES = {"amount", "date", "number", "percentage", "text"}
EXTRACTION_METHODS = {
    "browser_visible_text",
    "embedded_text",
    "native_text",
    "none",
    "paddle_ocr",
}
APPROVING_ROLES = {"authorized_user", "professional_reviewer"}
AMBIGUOUS_NUMERIC_DATE_RE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _issue(
    issues: list[dict[str, str]],
    *,
    code: str,
    field: str,
    message: str,
    severity: str = "error",
) -> None:
    issues.append(
        {"code": code, "field": field, "message": message, "severity": severity}
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_iso_date(value: Any, *, precision: str = "day") -> bool:
    if not isinstance(value, str) or AMBIGUOUS_NUMERIC_DATE_RE.fullmatch(value):
        return False
    if precision == "year":
        return bool(re.fullmatch(r"\d{4}", value))
    if precision == "month":
        if not re.fullmatch(r"\d{4}-\d{2}", value):
            return False
        try:
            date.fromisoformat(f"{value}-01")
        except ValueError:
            return False
        return True
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _source_records_sha256(records: dict[str, Any]) -> str:
    source = dict(records)
    source.pop("validation", None)
    raw = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _locator_key(document_id: str, locator: dict[str, Any]) -> tuple[str, str, str]:
    return (
        document_id,
        str(locator.get("kind", "")),
        str(locator.get("value", "")),
    )


def _normalize_quote(value: str) -> str:
    return " ".join(value.split())


def _fragment_requires_visual_confirmation(fragment: dict[str, Any]) -> bool:
    """Return whether extraction quality requires comparison with the page."""

    if fragment.get("extraction_method") in {"browser_visible_text", "paddle_ocr"}:
        return True
    requiring_limitations = {
        "browser_capture_text_requires_visual_confirmation",
        "embedded_text_below_ocr_quality_threshold",
        "ocr_text_requires_visual_confirmation",
    }
    limitations = fragment.get("limitations", [])
    if isinstance(limitations, str):
        return limitations in requiring_limitations
    if not isinstance(limitations, list):
        return False
    return bool(requiring_limitations.intersection(map(str, limitations)))


def _validate_ocr_visual_confirmation(
    anchor: dict[str, Any],
    *,
    anchor_path: str,
    issues: list[dict[str, str]],
) -> None:
    """Require a human visual check before OCR text can confirm a fact."""

    confirmation = anchor.get("visual_confirmation")
    if not isinstance(confirmation, dict):
        _issue(
            issues,
            code="missing_ocr_visual_confirmation",
            field=f"{anchor_path}.visual_confirmation",
            message=(
                "A confirmed fact citing OCR-derived, browser-captured, or mechanically weak text "
                "requires a per-anchor visual confirmation by an authorized "
                "human reviewer."
            ),
        )
        return
    if confirmation.get("confirmed") is not True:
        _issue(
            issues,
            code="unconfirmed_ocr_visual_confirmation",
            field=f"{anchor_path}.visual_confirmation.confirmed",
            message="Visual confirmation of the extracted quote must be explicitly true.",
        )
    if not _nonempty(confirmation.get("confirmed_by_id")):
        _issue(
            issues,
            code="missing_ocr_visual_confirmation_actor_id",
            field=f"{anchor_path}.visual_confirmation.confirmed_by_id",
            message="Record a stable identifier for the human who checked the page image.",
        )
    if confirmation.get("confirmed_by_role") not in APPROVING_ROLES:
        _issue(
            issues,
            code="invalid_ocr_visual_confirmation_role",
            field=f"{anchor_path}.visual_confirmation.confirmed_by_role",
            message=(
                "Extracted-text visual confirmation must come from an authorized user or "
                "professional reviewer, never the model."
            ),
        )
    if not _validate_iso_datetime(confirmation.get("recorded_at")):
        _issue(
            issues,
            code="invalid_ocr_visual_confirmation_timestamp",
            field=f"{anchor_path}.visual_confirmation.recorded_at",
            message="Extracted-text visual confirmation needs an ISO date-time with timezone.",
        )
    if not _nonempty(confirmation.get("basis")):
        _issue(
            issues,
            code="missing_ocr_visual_confirmation_basis",
            field=f"{anchor_path}.visual_confirmation.basis",
            message="Record how the OCR quote was checked against the source page image.",
        )


def _inventory_maps(
    inventory: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str], dict[str, Any]]]:
    documents = {
        str(record.get("document_id")): record
        for record in inventory.get("documents", [])
        if isinstance(record, dict) and record.get("document_id")
    }
    fragments: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fragment in inventory.get("evidence_fragments", []):
        if not isinstance(fragment, dict) or not isinstance(
            fragment.get("locator"), dict
        ):
            continue
        key = _locator_key(str(fragment.get("document_id", "")), fragment["locator"])
        fragments[key] = fragment
    return documents, fragments


def _validate_material_decisions(
    records: dict[str, Any], issues: list[dict[str, str]]
) -> None:
    decisions = records.get("material_decisions")
    required = (
        "professional_question_confirmed",
        "framework_confirmed",
        "period_scope_confirmed",
        "ambiguous_terms_resolved",
    )
    if not isinstance(decisions, dict):
        _issue(
            issues,
            code="missing_material_decisions",
            field="material_decisions",
            message="Material decisions must be recorded explicitly.",
        )
        return
    for name in required:
        if decisions.get(name) is not True:
            _issue(
                issues,
                code="unconfirmed_material_decision",
                field=f"material_decisions.{name}",
                message="The decision must be explicitly confirmed before validation.",
            )

    decision_log = records.get("decision_log")
    if not isinstance(decision_log, list):
        _issue(
            issues,
            code="missing_decision_log",
            field="decision_log",
            message="Each material gate needs an auditable reviewer decision record.",
        )
        return
    covered: set[str] = set()
    decision_ids: set[str] = set()
    for index, record in enumerate(decision_log):
        field = f"decision_log[{index}]"
        if not isinstance(record, dict):
            _issue(
                issues,
                code="invalid_decision_record",
                field=field,
                message="Decision record must be an object.",
            )
            continue
        decision_id = str(record.get("decision_id", "")).strip()
        if not decision_id or decision_id in decision_ids:
            _issue(
                issues,
                code="invalid_or_duplicate_decision_id",
                field=f"{field}.decision_id",
                message="decision_id must be non-empty and unique.",
            )
        else:
            decision_ids.add(decision_id)
        gate = str(record.get("gate", ""))
        if gate not in required or gate in covered:
            _issue(
                issues,
                code="invalid_or_duplicate_decision_gate",
                field=f"{field}.gate",
                message="Each required material gate must appear exactly once.",
            )
        else:
            covered.add(gate)
        if record.get("decision") is not True:
            _issue(
                issues,
                code="unconfirmed_decision_record",
                field=f"{field}.decision",
                message="The recorded reviewer decision must be explicitly true.",
            )
        if record.get("decided_by_role") not in APPROVING_ROLES:
            _issue(
                issues,
                code="missing_decision_authority",
                field=f"{field}.decided_by_role",
                message="Decision role must be an authorized user or professional reviewer, never the model.",
            )
        if not _nonempty(record.get("decided_by_id")):
            _issue(
                issues,
                code="missing_decision_actor_id",
                field=f"{field}.decided_by_id",
                message="Record a stable reviewer or user ID without exposing unnecessary personal data.",
            )
        if not _validate_iso_datetime(record.get("recorded_at")):
            _issue(
                issues,
                code="invalid_decision_timestamp",
                field=f"{field}.recorded_at",
                message="Decision timestamp must be an ISO date-time with timezone.",
            )
        if not _nonempty(record.get("basis")):
            _issue(
                issues,
                code="missing_decision_basis",
                field=f"{field}.basis",
                message="Record the document or user instruction supporting the decision.",
            )
    missing_gates = sorted(set(required) - covered)
    if missing_gates:
        _issue(
            issues,
            code="incomplete_decision_log",
            field="decision_log",
            message=f"Missing decision records for: {', '.join(missing_gates)}.",
        )


def _validate_processing_authorization(
    records: dict[str, Any], issues: list[dict[str, str]]
) -> None:
    authorization = records.get("processing_authorization")
    if not isinstance(authorization, dict):
        _issue(
            issues,
            code="missing_processing_authorization",
            field="processing_authorization",
            message="Studio and model-processing authority must be recorded before semantic review.",
        )
        return
    true_fields = (
        "studio_processing_authorized",
        "model_processing_approved",
        "personal_data_minimized",
    )
    for name in true_fields:
        if authorization.get(name) is not True:
            _issue(
                issues,
                code="unconfirmed_processing_authorization",
                field=f"processing_authorization.{name}",
                message="Processing authorization and data minimization must be explicit.",
            )
    for name in ("processor_scope", "approved_by_id", "basis"):
        if not _nonempty(authorization.get(name)):
            _issue(
                issues,
                code="incomplete_processing_authorization",
                field=f"processing_authorization.{name}",
                message="Processing authorization field must be non-empty.",
            )
    if authorization.get("approved_by_role") not in APPROVING_ROLES:
        _issue(
            issues,
            code="invalid_processing_approver_role",
            field="processing_authorization.approved_by_role",
            message="Processing must be approved by an authorized user or professional reviewer.",
        )
    if not _validate_iso_datetime(authorization.get("recorded_at")):
        _issue(
            issues,
            code="invalid_processing_authorization_timestamp",
            field="processing_authorization.recorded_at",
            message="Processing authorization needs an ISO date-time with timezone.",
        )


def _validate_fact_evidence(
    fact: dict[str, Any],
    *,
    review_status: str,
    fact_path: str,
    documents: dict[str, dict[str, Any]],
    fragments: dict[tuple[str, str, str], dict[str, Any]],
    inventory_dir: Path,
    issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    evidence = fact.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        _issue(
            issues,
            code="missing_fact_provenance",
            field=f"{fact_path}.evidence",
            message="Every fact requires at least one document locator and quote.",
        )
        return []
    valid_evidence: list[dict[str, Any]] = []
    for evidence_index, anchor in enumerate(evidence):
        anchor_path = f"{fact_path}.evidence[{evidence_index}]"
        if not isinstance(anchor, dict):
            _issue(
                issues,
                code="invalid_evidence_anchor",
                field=anchor_path,
                message="Evidence anchor must be an object.",
            )
            continue
        document_id = str(anchor.get("document_id", ""))
        locator = anchor.get("locator")
        quote = anchor.get("quote")
        if not safe_identifier(document_id):
            _issue(
                issues,
                code="unsafe_document_id",
                field=f"{anchor_path}.document_id",
                message="Evidence document IDs must be opaque and identifier-free.",
            )
            continue
        if document_id not in documents:
            _issue(
                issues,
                code="unknown_document_reference",
                field=f"{anchor_path}.document_id",
                message="Evidence document ID is not present in the inventory.",
            )
            continue
        if not isinstance(locator, dict):
            _issue(
                issues,
                code="missing_evidence_locator",
                field=f"{anchor_path}.locator",
                message="Evidence locator must identify a page, sheet, or document fragment.",
            )
            continue
        if privacy_issue(locator.get("value")):
            _issue(
                issues,
                code="unsafe_evidence_locator",
                field=f"{anchor_path}.locator.value",
                message="Evidence locators must omit identifiers and private or tokenized URLs.",
            )
            continue
        fragment = fragments.get(_locator_key(document_id, locator))
        if fragment is None:
            _issue(
                issues,
                code="unknown_evidence_locator",
                field=f"{anchor_path}.locator",
                message="Locator does not match an extracted evidence fragment.",
            )
            continue
        extraction_method = fragment.get("extraction_method")
        if extraction_method not in EXTRACTION_METHODS:
            _issue(
                issues,
                code="missing_or_invalid_extraction_provenance",
                field=f"{anchor_path}.locator",
                message=(
                    "Referenced evidence must retain a recognized extraction "
                    "method from the generated inventory."
                ),
            )
        if review_status == "confirmed" and _fragment_requires_visual_confirmation(
            fragment
        ):
            _validate_ocr_visual_confirmation(
                anchor,
                anchor_path=anchor_path,
                issues=issues,
            )
        if not _nonempty(quote):
            _issue(
                issues,
                code="missing_evidence_quote",
                field=f"{anchor_path}.quote",
                message="Evidence quote must be non-empty.",
            )
            continue
        if privacy_issue(quote):
            _issue(
                issues,
                code="unsafe_evidence_quote",
                field=f"{anchor_path}.quote",
                message="Evidence quotes must omit raw identity, tax codes, email, and private URLs.",
            )
            continue
        raw_source_text = read_fragment_text(inventory_dir, fragment)
        expected_hash = str(fragment.get("text_sha256", ""))
        actual_hash = hashlib.sha256(raw_source_text.encode("utf-8")).hexdigest()
        if not expected_hash or actual_hash != expected_hash:
            _issue(
                issues,
                code="evidence_fragment_integrity_mismatch",
                field=f"{anchor_path}.locator",
                message="Extracted evidence no longer matches its inventory hash.",
            )
            continue
        source_text = _normalize_quote(raw_source_text)
        if _normalize_quote(str(quote)) not in source_text:
            _issue(
                issues,
                code="quote_not_found",
                field=f"{anchor_path}.quote",
                message="The normalized quote was not found in the referenced fragment.",
            )
            continue
        valid_evidence.append(anchor)
    return valid_evidence


def _validate_facts(
    records: dict[str, Any],
    *,
    documents: dict[str, dict[str, Any]],
    fragments: dict[tuple[str, str, str], dict[str, Any]],
    inventory_dir: Path,
    issues: list[dict[str, str]],
) -> set[str]:
    facts = records.get("facts")
    if not isinstance(facts, list) or not facts:
        _issue(
            issues,
            code="missing_facts",
            field="facts",
            message="At least one evidence-backed fact is required.",
        )
        return set()
    fact_ids: set[str] = set()
    for index, fact in enumerate(facts):
        fact_path = f"facts[{index}]"
        if not isinstance(fact, dict):
            _issue(
                issues,
                code="invalid_fact",
                field=fact_path,
                message="Fact must be an object.",
            )
            continue
        fact_id = str(fact.get("fact_id", "")).strip()
        if not safe_identifier(fact_id) or fact_id in fact_ids:
            _issue(
                issues,
                code="invalid_or_duplicate_fact_id",
                field=f"{fact_path}.fact_id",
                message="fact_id must be opaque, identifier-free, and unique.",
            )
        else:
            fact_ids.add(fact_id)
        if not _nonempty(fact.get("statement")):
            _issue(
                issues,
                code="missing_fact_statement",
                field=f"{fact_path}.statement",
                message="Fact statement must be non-empty.",
            )
        elif privacy_issue(fact.get("statement")):
            _issue(
                issues,
                code="unsafe_fact_statement",
                field=f"{fact_path}.statement",
                message="Fact statements must omit raw identifiers and private or tokenized URLs.",
            )
        if not _nonempty(fact.get("review_label")):
            _issue(
                issues,
                code="missing_safe_review_label",
                field=f"{fact_path}.review_label",
                message="A concise identifier-free review label is required.",
            )
        elif privacy_issue(fact.get("review_label")):
            _issue(
                issues,
                code="unsafe_fact_review_label",
                field=f"{fact_path}.review_label",
                message="Review labels must omit raw identity, tax codes, email, and private URLs.",
            )
        if "value" not in fact or fact.get("value") is None:
            _issue(
                issues,
                code="missing_fact_value",
                field=f"{fact_path}.value",
                message="Every fact must include an explicit value.",
            )
        elif privacy_issue(fact.get("value")):
            _issue(
                issues,
                code="unsafe_fact_value",
                field=f"{fact_path}.value",
                message="Review data fields must omit raw identifiers and private or tokenized URLs.",
            )
        value_type = str(fact.get("value_type", ""))
        if value_type not in VALUE_TYPES:
            _issue(
                issues,
                code="invalid_value_type",
                field=f"{fact_path}.value_type",
                message=f"Allowed value types: {', '.join(sorted(VALUE_TYPES))}.",
            )
        if value_type == "date" and not _validate_iso_date(fact.get("value")):
            _issue(
                issues,
                code="ambiguous_or_invalid_date",
                field=f"{fact_path}.value",
                message="Date facts must use an unambiguous ISO YYYY-MM-DD value.",
            )
        review_status = str(fact.get("review_status", ""))
        if review_status not in FACT_STATUSES:
            _issue(
                issues,
                code="invalid_fact_review_status",
                field=f"{fact_path}.review_status",
                message=f"Allowed statuses: {', '.join(sorted(FACT_STATUSES))}.",
            )
        elif review_status != "confirmed":
            _issue(
                issues,
                code="fact_not_confirmed",
                field=f"{fact_path}.review_status",
                message="Pending or disputed facts remain visible and cannot feed calculations.",
                severity="warning",
            )
        _validate_fact_evidence(
            fact,
            review_status=review_status,
            fact_path=fact_path,
            documents=documents,
            fragments=fragments,
            inventory_dir=inventory_dir,
            issues=issues,
        )
    return fact_ids


def _validate_timeline(
    records: dict[str, Any], fact_ids: set[str], issues: list[dict[str, str]]
) -> None:
    timeline = records.get("timeline", [])
    if not isinstance(timeline, list):
        _issue(
            issues,
            code="invalid_timeline",
            field="timeline",
            message="Timeline must be a list.",
        )
        return
    event_ids: set[str] = set()
    for index, event in enumerate(timeline):
        event_path = f"timeline[{index}]"
        if not isinstance(event, dict):
            _issue(
                issues,
                code="invalid_timeline_event",
                field=event_path,
                message="Timeline event must be an object.",
            )
            continue
        event_id = str(event.get("event_id", "")).strip()
        if not safe_identifier(event_id) or event_id in event_ids:
            _issue(
                issues,
                code="invalid_or_duplicate_event_id",
                field=f"{event_path}.event_id",
                message="event_id must be opaque, identifier-free, and unique.",
            )
        else:
            event_ids.add(event_id)
        if not _nonempty(event.get("description")):
            _issue(
                issues,
                code="missing_timeline_description",
                field=f"{event_path}.description",
                message="Timeline event description must be non-empty.",
            )
        elif privacy_issue(event.get("description")):
            _issue(
                issues,
                code="unsafe_timeline_description",
                field=f"{event_path}.description",
                message="Timeline descriptions must omit raw identifiers and private or tokenized URLs.",
            )
        precision = str(event.get("date_precision", ""))
        if precision not in DATE_PRECISIONS or not _validate_iso_date(
            event.get("date"), precision=precision
        ):
            _issue(
                issues,
                code="ambiguous_or_invalid_event_date",
                field=f"{event_path}.date",
                message="Event date must be unambiguous and match its declared precision.",
            )
        source_fact_ids = event.get("source_fact_ids")
        if not isinstance(source_fact_ids, list) or not source_fact_ids:
            _issue(
                issues,
                code="timeline_event_without_fact",
                field=f"{event_path}.source_fact_ids",
                message="Every timeline event must cite at least one fact.",
            )
        else:
            unknown = sorted(set(map(str, source_fact_ids)) - fact_ids)
            if unknown:
                _issue(
                    issues,
                    code="unknown_timeline_fact",
                    field=f"{event_path}.source_fact_ids",
                    message=f"Unknown fact ids: {', '.join(unknown)}.",
                )


def _write_timeline(path: Path, records: dict[str, Any]) -> None:
    events = [event for event in records.get("timeline", []) if isinstance(event, dict)]
    events.sort(
        key=lambda event: (str(event.get("date", "")), str(event.get("event_id", "")))
    )
    fieldnames = [
        "event_id",
        "date",
        "date_precision",
        "description",
        "source_fact_ids",
        "review_status",
        "conflict_group",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            writer.writerow(
                {
                    "event_id": event.get("event_id", ""),
                    "date": event.get("date", ""),
                    "date_precision": event.get("date_precision", ""),
                    "description": event.get("description", ""),
                    "source_fact_ids": ";".join(
                        map(str, event.get("source_fact_ids", []))
                    ),
                    "review_status": event.get("review_status", ""),
                    "conflict_group": event.get("conflict_group") or "",
                }
            )
    mark_private_file(path)


def _write_evidence_matrix(
    path: Path,
    records: dict[str, Any],
    fragments: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    fieldnames = [
        "fact_id",
        "statement",
        "review_status",
        "document_id",
        "locator_kind",
        "locator_value",
        "quote",
        "extraction_method",
        "visual_confirmation_required",
        "visual_confirmation_confirmed",
        "visual_confirmation_by_id",
        "visual_confirmation_by_role",
        "visual_confirmation_recorded_at",
        "visual_confirmation_basis",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for fact in records.get("facts", []):
            if not isinstance(fact, dict):
                continue
            for evidence in fact.get("evidence", []):
                if not isinstance(evidence, dict):
                    continue
                locator = evidence.get("locator", {})
                if not isinstance(locator, dict):
                    locator = {}
                fragment = fragments.get(
                    _locator_key(str(evidence.get("document_id", "")), locator), {}
                )
                confirmation = evidence.get("visual_confirmation", {})
                if not isinstance(confirmation, dict):
                    confirmation = {}
                writer.writerow(
                    {
                        "fact_id": fact.get("fact_id", ""),
                        "statement": fact.get("statement", ""),
                        "review_status": fact.get("review_status", ""),
                        "document_id": evidence.get("document_id", ""),
                        "locator_kind": locator.get("kind", ""),
                        "locator_value": locator.get("value", ""),
                        "quote": evidence.get("quote", ""),
                        "extraction_method": fragment.get("extraction_method", ""),
                        "visual_confirmation_required": (
                            _fragment_requires_visual_confirmation(fragment)
                        ),
                        "visual_confirmation_confirmed": confirmation.get(
                            "confirmed", ""
                        ),
                        "visual_confirmation_by_id": confirmation.get(
                            "confirmed_by_id", ""
                        ),
                        "visual_confirmation_by_role": confirmation.get(
                            "confirmed_by_role", ""
                        ),
                        "visual_confirmation_recorded_at": confirmation.get(
                            "recorded_at", ""
                        ),
                        "visual_confirmation_basis": confirmation.get("basis", ""),
                    }
                )
    mark_private_file(path)


def validate_case_records(
    records_path: Path, inventory_path: Path, output_dir: Path
) -> dict[str, Any]:
    """Validate record shape and provenance without interpreting legal meaning."""

    records = _load_object(records_path)
    inventory = _load_object(inventory_path)
    documents, fragments = _inventory_maps(inventory)
    issues: list[dict[str, str]] = []
    acquisition_binding: dict[str, Any] | None = None

    if inventory_path.resolve() != (output_dir / "file_inventory.json").resolve():
        _issue(
            issues,
            code="inventory_outside_case_run",
            field="inventory_path",
            message="Validation must use file_inventory.json from the case run directory.",
        )
    else:
        try:
            acquisition_binding = build_acquisition_binding(
                inventory_path, output_dir / "run_intake.json"
            )
        except AcquisitionBindingError:
            _issue(
                issues,
                code="unverifiable_acquisition_binding",
                field="run_intake.json",
                message="Inventory and acquisition posture must be present and verifiable before validation.",
            )

    if not _nonempty(records.get("professional_question")):
        _issue(
            issues,
            code="missing_professional_question",
            field="professional_question",
            message="The professional question must be stated explicitly.",
        )
    elif privacy_issue(records.get("professional_question")):
        _issue(
            issues,
            code="unsafe_professional_question",
            field="professional_question",
            message="The professional question must omit raw identifiers and private or tokenized URLs.",
        )
    _validate_processing_authorization(records, issues)
    _validate_material_decisions(records, issues)
    fact_ids = _validate_facts(
        records,
        documents=documents,
        fragments=fragments,
        inventory_dir=inventory_path.parent,
        issues=issues,
    )
    _validate_timeline(records, fact_ids, issues)

    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    audit = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "status": "schema_error" if error_count else "passed",
        "validated_at": _utc_now(),
        "records_path": records_path.resolve().as_posix(),
        "inventory_path": inventory_path.resolve().as_posix(),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "deterministic_scope": [
            "schema",
            "identifier_references",
            "date_format",
            "locator_existence",
            "normalized_quote_presence",
            "ocr_visual_confirmation_authority",
        ],
        "semantic_scope": "not_performed",
        "acquisition_binding": acquisition_binding,
    }
    prepare_private_directory(output_dir)
    if error_count:
        write_json(output_dir / "case_records_audit.json", audit)
        return audit

    validated = dict(records)
    source_records_sha256 = _source_records_sha256(records)
    validated["validation"] = {
        "status": "passed",
        "validated_at": audit["validated_at"],
        "warning_count": warning_count,
        "source_records_sha256": source_records_sha256,
        "acquisition_binding": acquisition_binding,
    }
    validated_path = write_json(output_dir / "case_records_validated.json", validated)
    audit["source_records_sha256"] = source_records_sha256
    audit["validated_output_path"] = validated_path.resolve().as_posix()
    write_json(output_dir / "case_records_audit.json", audit)
    _write_timeline(output_dir / "timeline.csv", validated)
    _write_evidence_matrix(output_dir / "evidence_matrix.csv", validated, fragments)
    return audit


def main(argv: list[str] | None = None) -> int:
    """Run record validation and write audit artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output_dir = ensure_safe_output_dir(args.output_dir, plugin_root=PLUGIN_ROOT)
        audit = validate_case_records(args.records, args.inventory, output_dir)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        PermissionError,
        ValueError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 1
    if audit["error_count"]:
        LOGGER.error(
            "Case record validation failed with %s error(s).", audit["error_count"]
        )
        return 1
    LOGGER.info("Case records validated with %s warning(s).", audit["warning_count"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
