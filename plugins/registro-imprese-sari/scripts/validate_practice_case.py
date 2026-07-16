"""Validate a source-backed Registro Imprese/DIRE practice draft mechanically."""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    ensure_safe_output_dir,
    load_json_object,
    safe_identifier,
    sha256_file,
    validate_iso_date,
    validate_official_source_url,
    write_private_json,
)

__all__ = ["validate_practice_case", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_POSITION_TYPES = {
    "registro_imprese",
    "rea",
    "agenzia_entrate",
    "inps",
    "inail",
    "suap",
    "ivass_rui",
    "other",
}
CONFIRMATION_STATUSES = {"confirmed", "needs_professional_review", "unknown"}
ITEM_REVIEW_STATUSES = {"proposed", "confirmed", "not_applicable", "blocked"}
PLAN_ARRAYS = (
    "classification_proposals",
    "position_matrix",
    "dire_steps",
    "required_documents",
    "application_fields",
    "risks",
    "missing_information",
)
BANNED_PRIVATE_KEYS = {
    "client_name",
    "full_name",
    "nome_cliente",
    "codice_fiscale",
    "tax_code",
    "partita_iva",
    "vat_number",
    "email",
    "pec",
    "phone",
    "telefono",
    "street_address",
    "indirizzo",
}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
ITALIAN_TAX_CODE_RE = re.compile(
    r"\b[A-Z]{6}[0-9]{2}[A-EHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
    re.IGNORECASE,
)
ITALIAN_VAT_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?39[ .-]?)?(?:0\d{1,3}|3\d{2})[ .-]?\d{5,8}(?!\w)")
MODEL_ROLES = {"ai", "assistant", "codex", "llm", "model"}


def _issue(
    issues: list[dict[str, Any]],
    *,
    code: str,
    path: str,
    message: str,
    severity: str = "error",
) -> None:
    issues.append(
        {"code": code, "path": path, "message": message, "severity": severity}
    )


def _nonempty_text(
    value: object,
    *,
    path: str,
    issues: list[dict[str, Any]],
    max_length: int = 10_000,
) -> str:
    text = str(value or "").strip()
    if not text:
        _issue(issues, code="missing_text", path=path, message="value is required")
    elif len(text) > max_length:
        _issue(
            issues,
            code="text_too_long",
            path=path,
            message=f"value exceeds {max_length} characters",
        )
    return text


def _validate_timestamp(
    value: object, *, path: str, issues: list[dict[str, Any]]
) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _issue(
            issues,
            code="invalid_timestamp",
            path=path,
            message="timestamp must use ISO 8601",
        )
        return text
    if parsed.tzinfo is None:
        _issue(
            issues,
            code="timestamp_missing_timezone",
            path=path,
            message="timestamp must include a timezone",
        )
    return text


def _walk_privacy(
    value: object,
    *,
    path: str,
    issues: list[dict[str, Any]],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key).lower() in BANNED_PRIVATE_KEYS:
                _issue(
                    issues,
                    code="direct_identifier_field_forbidden",
                    path=child_path,
                    message="case JSON must use a pseudonymous client_reference",
                )
            _walk_privacy(child, path=child_path, issues=issues)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_privacy(child, path=f"{path}[{index}]", issues=issues)
    elif isinstance(value, str):
        if EMAIL_RE.search(value):
            _issue(
                issues,
                code="email_in_minimized_case_json",
                path=path,
                message="remove direct email addresses from the minimized case JSON",
            )
        if ITALIAN_TAX_CODE_RE.search(value):
            _issue(
                issues,
                code="tax_code_in_minimized_case_json",
                path=path,
                message="remove Italian tax codes from the minimized case JSON",
            )
        if ITALIAN_VAT_RE.search(value):
            _issue(
                issues,
                code="eleven_digit_identifier_in_minimized_case_json",
                path=path,
                message="remove eleven-digit identifiers from the minimized case JSON",
            )
        if PHONE_RE.search(value):
            _issue(
                issues,
                code="phone_in_minimized_case_json",
                path=path,
                message="remove phone numbers from the minimized case JSON",
            )


def _validate_case_intake(
    intake: dict[str, Any], *, issues: list[dict[str, Any]]
) -> tuple[str, set[str]]:
    if intake.get("schema_version") != "1.0":
        _issue(
            issues,
            code="schema_version_mismatch",
            path="case_intake.schema_version",
            message="expected 1.0",
        )
    if intake.get("plugin") != PLUGIN_NAME:
        _issue(
            issues,
            code="plugin_mismatch",
            path="case_intake.plugin",
            message=f"expected {PLUGIN_NAME}",
        )
    try:
        run_id = safe_identifier(intake.get("run_id"), field="case_intake.run_id")
    except ValueError as exc:
        _issue(
            issues,
            code="invalid_run_id",
            path="case_intake.run_id",
            message=str(exc),
        )
        run_id = "invalid"
    try:
        safe_identifier(
            intake.get("client_reference"), field="case_intake.client_reference"
        )
    except ValueError as exc:
        _issue(
            issues,
            code="invalid_client_reference",
            path="case_intake.client_reference",
            message=str(exc),
        )
    try:
        validate_iso_date(intake.get("reference_date"), field="reference_date")
    except ValueError as exc:
        _issue(
            issues,
            code="invalid_reference_date",
            path="case_intake.reference_date",
            message=str(exc),
        )

    fact_ids = {
        "CASE-CHAMBER",
        "CASE-SUBJECT",
        "CASE-ACTIVITY",
        "CASE-OPERATION",
        "CASE-EFFECTIVE-DATE",
        "CASE-PROFESSIONAL-QUESTION",
    }
    chamber = intake.get("competent_chamber")
    if not isinstance(chamber, dict):
        _issue(
            issues,
            code="missing_object",
            path="case_intake.competent_chamber",
            message="object is required",
        )
    else:
        _nonempty_text(
            chamber.get("tenant"),
            path="case_intake.competent_chamber.tenant",
            issues=issues,
        )
        _nonempty_text(
            chamber.get("name"),
            path="case_intake.competent_chamber.name",
            issues=issues,
        )
        _nonempty_text(
            chamber.get("territorial_basis"),
            path="case_intake.competent_chamber.territorial_basis",
            issues=issues,
        )
        status = chamber.get("confirmation_status")
        if status not in CONFIRMATION_STATUSES:
            _issue(
                issues,
                code="invalid_confirmation_status",
                path="case_intake.competent_chamber.confirmation_status",
                message="unsupported status",
            )
        elif status != "confirmed":
            _issue(
                issues,
                code="competent_chamber_unconfirmed",
                path="case_intake.competent_chamber.confirmation_status",
                message="competent chamber requires professional confirmation",
                severity="blocker",
            )

    subject = intake.get("subject")
    if not isinstance(subject, dict):
        _issue(
            issues,
            code="missing_object",
            path="case_intake.subject",
            message="object is required",
        )
    else:
        _nonempty_text(
            subject.get("legal_form"),
            path="case_intake.subject.legal_form",
            issues=issues,
        )
        status = subject.get("confirmation_status")
        if status not in CONFIRMATION_STATUSES:
            _issue(
                issues,
                code="invalid_confirmation_status",
                path="case_intake.subject.confirmation_status",
                message="unsupported status",
            )
        elif status != "confirmed":
            _issue(
                issues,
                code="legal_form_unconfirmed",
                path="case_intake.subject.confirmation_status",
                message="legal form requires professional confirmation",
                severity="blocker",
            )

    activity = intake.get("activity")
    if not isinstance(activity, dict):
        _issue(
            issues,
            code="missing_object",
            path="case_intake.activity",
            message="object is required",
        )
    else:
        _nonempty_text(
            activity.get("description"),
            path="case_intake.activity.description",
            issues=issues,
        )
        status = activity.get("classification_status")
        if status not in CONFIRMATION_STATUSES:
            _issue(
                issues,
                code="invalid_confirmation_status",
                path="case_intake.activity.classification_status",
                message="unsupported status",
            )
        elif status != "confirmed":
            _issue(
                issues,
                code="activity_classification_unconfirmed",
                path="case_intake.activity.classification_status",
                message="activity description/classification requires professional confirmation",
                severity="blocker",
            )

    operation = intake.get("requested_operation")
    if not isinstance(operation, dict):
        _issue(
            issues,
            code="missing_object",
            path="case_intake.requested_operation",
            message="object is required",
        )
    else:
        _nonempty_text(
            operation.get("description"),
            path="case_intake.requested_operation.description",
            issues=issues,
        )
        positions = operation.get("position_types")
        if not isinstance(positions, list) or not positions:
            _issue(
                issues,
                code="position_types_unresolved",
                path="case_intake.requested_operation.position_types",
                message="at least one proposed position type is required",
                severity="blocker",
            )
        else:
            invalid = sorted({str(item) for item in positions} - ALLOWED_POSITION_TYPES)
            if invalid:
                _issue(
                    issues,
                    code="invalid_position_type",
                    path="case_intake.requested_operation.position_types",
                    message="unsupported values: " + ", ".join(invalid),
                )
            if len(positions) != len(set(map(str, positions))):
                _issue(
                    issues,
                    code="duplicate_position_type",
                    path="case_intake.requested_operation.position_types",
                    message="position types must be unique",
                )
        effective_date = operation.get("effective_date")
        if effective_date is None or str(effective_date).strip() == "":
            _issue(
                issues,
                code="effective_date_unresolved",
                path="case_intake.requested_operation.effective_date",
                message="effective date is required before a DIRE plan can be finalized",
                severity="blocker",
            )
        else:
            try:
                validate_iso_date(effective_date, field="effective_date")
            except ValueError as exc:
                _issue(
                    issues,
                    code="invalid_effective_date",
                    path="case_intake.requested_operation.effective_date",
                    message=str(exc),
                )
        status = operation.get("confirmation_status")
        if status not in CONFIRMATION_STATUSES:
            _issue(
                issues,
                code="invalid_confirmation_status",
                path="case_intake.requested_operation.confirmation_status",
                message="unsupported status",
            )
        elif status != "confirmed":
            _issue(
                issues,
                code="requested_operation_unconfirmed",
                path="case_intake.requested_operation.confirmation_status",
                message="requested position opening scope requires professional confirmation",
                severity="blocker",
            )

    _nonempty_text(
        intake.get("professional_question"),
        path="case_intake.professional_question",
        issues=issues,
    )
    authorization = intake.get("processing_authorization")
    if not isinstance(authorization, dict):
        _issue(
            issues,
            code="processing_authorization_missing",
            path="case_intake.processing_authorization",
            message="explicit case-material processing authorization is required",
        )
    else:
        if authorization.get("approved") is not True:
            _issue(
                issues,
                code="processing_not_approved",
                path="case_intake.processing_authorization.approved",
                message="processing authorization must be true",
            )
        _nonempty_text(
            authorization.get("approval_id"),
            path="case_intake.processing_authorization.approval_id",
            issues=issues,
            max_length=200,
        )
        role = _nonempty_text(
            authorization.get("approved_by_role"),
            path="case_intake.processing_authorization.approved_by_role",
            issues=issues,
            max_length=120,
        )
        if role.casefold() in MODEL_ROLES:
            _issue(
                issues,
                code="model_cannot_authorize_processing",
                path="case_intake.processing_authorization.approved_by_role",
                message="authorization must come from a human with authority",
            )
        _validate_timestamp(
            authorization.get("recorded_at"),
            path="case_intake.processing_authorization.recorded_at",
            issues=issues,
        )
    return run_id, fact_ids


def _validate_source_manifest(
    manifest: dict[str, Any],
    *,
    run_id: str,
    output_dir: Path,
    issues: list[dict[str, Any]],
) -> set[str]:
    if manifest.get("plugin") != PLUGIN_NAME:
        _issue(
            issues,
            code="source_manifest_plugin_mismatch",
            path="official_sources.plugin",
            message=f"expected {PLUGIN_NAME}",
        )
    if manifest.get("run_id") != run_id:
        _issue(
            issues,
            code="source_manifest_run_mismatch",
            path="official_sources.run_id",
            message="run id must match case intake",
        )
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        _issue(
            issues,
            code="official_sources_missing",
            path="official_sources.sources",
            message="select at least one official source",
        )
        return set()
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        path = f"official_sources.sources[{index}]"
        if not isinstance(source, dict):
            _issue(
                issues,
                code="source_not_object",
                path=path,
                message="source must be an object",
            )
            continue
        try:
            source_id = safe_identifier(
                source.get("source_id"), field=f"{path}.source_id"
            )
        except ValueError as exc:
            _issue(
                issues,
                code="invalid_source_id",
                path=f"{path}.source_id",
                message=str(exc),
            )
            continue
        if source_id in source_ids:
            _issue(
                issues,
                code="duplicate_source_id",
                path=f"{path}.source_id",
                message=f"duplicate source id {source_id}",
            )
        source_ids.add(source_id)
        _nonempty_text(
            source.get("title") or source.get("chamber_title"),
            path=f"{path}.title",
            issues=issues,
        )
        _nonempty_text(source.get("publisher"), path=f"{path}.publisher", issues=issues)
        _nonempty_text(
            source.get("territorial_applicability") or source.get("chamber_title"),
            path=f"{path}.territorial_applicability",
            issues=issues,
        )
        try:
            validate_official_source_url(source.get("official_url"))
        except ValueError as exc:
            _issue(
                issues,
                code="invalid_official_source_url",
                path=f"{path}.official_url",
                message=str(exc),
            )
        source_timestamp = source.get("retrieved_at") or source.get("registered_at")
        if not source_timestamp:
            _issue(
                issues,
                code="source_timestamp_missing",
                path=path,
                message="source retrieval or registration timestamp is required",
            )
        else:
            _validate_timestamp(
                source_timestamp,
                path=f"{path}.retrieved_or_registered_at",
                issues=issues,
            )
        if source.get("updated_date"):
            try:
                validate_iso_date(
                    source.get("updated_date"), field=f"{path}.updated_date"
                )
            except ValueError as exc:
                _issue(
                    issues,
                    code="invalid_source_updated_date",
                    path=f"{path}.updated_date",
                    message=str(exc),
                )
        _nonempty_text(
            source.get("selection_status") or source.get("applicability_status"),
            path=f"{path}.applicability_status",
            issues=issues,
        )
        artifact_path = source.get("artifact_path")
        artifact_hash = source.get("artifact_sha256")
        if artifact_path:
            absolute = (output_dir / str(artifact_path)).resolve()
            if output_dir not in absolute.parents:
                _issue(
                    issues,
                    code="source_artifact_outside_run",
                    path=f"{path}.artifact_path",
                    message="source artifact must stay inside the run directory",
                )
            elif not absolute.is_file() or absolute.is_symlink():
                _issue(
                    issues,
                    code="source_artifact_missing",
                    path=f"{path}.artifact_path",
                    message="registered source artifact is missing",
                )
            elif not artifact_hash or sha256_file(absolute) != artifact_hash:
                _issue(
                    issues,
                    code="source_artifact_integrity_mismatch",
                    path=f"{path}.artifact_sha256",
                    message="registered source artifact hash does not match",
                )
    return source_ids


def _validate_confirmation(
    confirmation: object,
    *,
    path: str,
    issues: list[dict[str, Any]],
) -> None:
    if not isinstance(confirmation, dict):
        _issue(
            issues,
            code="professional_confirmation_missing",
            path=path,
            message="confirmed item requires a confirmation object",
        )
        return
    _nonempty_text(
        confirmation.get("confirmed_by_id"),
        path=f"{path}.confirmed_by_id",
        issues=issues,
        max_length=120,
    )
    role = _nonempty_text(
        confirmation.get("confirmed_by_role"),
        path=f"{path}.confirmed_by_role",
        issues=issues,
        max_length=120,
    )
    if role.casefold() in MODEL_ROLES or "professional" not in role.casefold():
        _issue(
            issues,
            code="invalid_confirmation_authority",
            path=f"{path}.confirmed_by_role",
            message="confirmed items require a professional human reviewer role",
        )
    _validate_timestamp(
        confirmation.get("confirmed_at"),
        path=f"{path}.confirmed_at",
        issues=issues,
    )
    _nonempty_text(
        confirmation.get("basis"),
        path=f"{path}.basis",
        issues=issues,
    )


def _validate_plan(
    plan: dict[str, Any],
    *,
    run_id: str,
    fact_ids: set[str],
    source_ids: set[str],
    issues: list[dict[str, Any]],
) -> dict[str, int]:
    if plan.get("schema_version") != "1.0":
        _issue(
            issues,
            code="schema_version_mismatch",
            path="practice_plan.schema_version",
            message="expected 1.0",
        )
    if plan.get("plugin") != PLUGIN_NAME:
        _issue(
            issues,
            code="plugin_mismatch",
            path="practice_plan.plugin",
            message=f"expected {PLUGIN_NAME}",
        )
    if plan.get("run_id") != run_id:
        _issue(
            issues,
            code="plan_run_mismatch",
            path="practice_plan.run_id",
            message="run id must match case intake",
        )
    _nonempty_text(
        plan.get("case_summary"), path="practice_plan.case_summary", issues=issues
    )
    all_source_ids = {"CASE-INTAKE", *source_ids}
    seen_item_ids: set[str] = set()
    review_counts = {status: 0 for status in ITEM_REVIEW_STATUSES}
    for array_name in PLAN_ARRAYS:
        items = plan.get(array_name)
        if not isinstance(items, list):
            _issue(
                issues,
                code="plan_array_missing",
                path=f"practice_plan.{array_name}",
                message="array is required",
            )
            continue
        if array_name in {"position_matrix", "dire_steps"} and not items:
            _issue(
                issues,
                code="material_plan_section_empty",
                path=f"practice_plan.{array_name}",
                message="at least one source-backed proposal is required",
                severity="blocker",
            )
        for index, item in enumerate(items):
            path = f"practice_plan.{array_name}[{index}]"
            if not isinstance(item, dict):
                _issue(
                    issues,
                    code="plan_item_not_object",
                    path=path,
                    message="item must be an object",
                )
                continue
            try:
                item_id = safe_identifier(item.get("id"), field=f"{path}.id")
            except ValueError as exc:
                _issue(
                    issues,
                    code="invalid_plan_item_id",
                    path=f"{path}.id",
                    message=str(exc),
                )
                item_id = ""
            if item_id in seen_item_ids:
                _issue(
                    issues,
                    code="duplicate_plan_item_id",
                    path=f"{path}.id",
                    message=f"duplicate item id {item_id}",
                )
            if item_id:
                seen_item_ids.add(item_id)
            _nonempty_text(item.get("title"), path=f"{path}.title", issues=issues)
            _nonempty_text(item.get("detail"), path=f"{path}.detail", issues=issues)
            item_sources = item.get("source_ids")
            if not isinstance(item_sources, list) or not item_sources:
                _issue(
                    issues,
                    code="item_sources_missing",
                    path=f"{path}.source_ids",
                    message="every proposal must cite at least one source",
                )
            else:
                unknown_sources = sorted(set(map(str, item_sources)) - all_source_ids)
                if unknown_sources:
                    _issue(
                        issues,
                        code="unknown_source_reference",
                        path=f"{path}.source_ids",
                        message="unknown source ids: " + ", ".join(unknown_sources),
                    )
                if len(item_sources) != len(set(map(str, item_sources))):
                    _issue(
                        issues,
                        code="duplicate_source_reference",
                        path=f"{path}.source_ids",
                        message="source ids must be unique",
                    )
            item_fact_ids = item.get("case_fact_ids")
            if not isinstance(item_fact_ids, list):
                _issue(
                    issues,
                    code="case_fact_ids_missing",
                    path=f"{path}.case_fact_ids",
                    message="case fact dependency array is required",
                )
            else:
                unknown_facts = sorted(set(map(str, item_fact_ids)) - fact_ids)
                if unknown_facts:
                    _issue(
                        issues,
                        code="unknown_case_fact_reference",
                        path=f"{path}.case_fact_ids",
                        message="unknown case fact ids: " + ", ".join(unknown_facts),
                    )
            review_status = item.get("review_status")
            if review_status not in ITEM_REVIEW_STATUSES:
                _issue(
                    issues,
                    code="invalid_item_review_status",
                    path=f"{path}.review_status",
                    message="unsupported review status",
                )
            else:
                review_counts[str(review_status)] += 1
                if review_status == "confirmed":
                    _validate_confirmation(
                        item.get("confirmation"),
                        path=f"{path}.confirmation",
                        issues=issues,
                    )
                elif review_status in {"proposed", "blocked"}:
                    _issue(
                        issues,
                        code="plan_item_requires_review",
                        path=f"{path}.review_status",
                        message=f"{array_name} item {item_id or index} is {review_status}",
                        severity="blocker",
                    )
    _nonempty_text(
        plan.get("sari_question_draft"),
        path="practice_plan.sari_question_draft",
        issues=issues,
    )
    limitations = plan.get("limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        _issue(
            issues,
            code="limitations_missing",
            path="practice_plan.limitations",
            message="non-empty limitations are required",
        )
    else:
        combined = " ".join(limitations).casefold()
        if "revisione professionale" not in combined:
            _issue(
                issues,
                code="professional_review_disclaimer_missing",
                path="practice_plan.limitations",
                message="limitations must state that this is a professional-review draft",
            )
        if not any(
            term in combined for term in ("nessun accesso", "non accede", "non invia")
        ):
            _issue(
                issues,
                code="no_submission_disclaimer_missing",
                path="practice_plan.limitations",
                message="limitations must state that no portal access or submission occurs",
            )
    professional_review = plan.get("professional_review")
    if not isinstance(professional_review, dict):
        _issue(
            issues,
            code="professional_review_missing",
            path="practice_plan.professional_review",
            message="professional review object is required",
        )
    else:
        status = professional_review.get("status")
        if status not in {"pending", "reviewed", "rejected"}:
            _issue(
                issues,
                code="invalid_professional_review_status",
                path="practice_plan.professional_review.status",
                message="unsupported status",
            )
        elif status != "reviewed":
            _issue(
                issues,
                code="professional_review_pending",
                path="practice_plan.professional_review.status",
                message=f"professional review is {status}",
                severity="blocker",
            )
        else:
            reviewer_id = _nonempty_text(
                professional_review.get("reviewer_id"),
                path="practice_plan.professional_review.reviewer_id",
                issues=issues,
                max_length=120,
            )
            del reviewer_id
            role = _nonempty_text(
                professional_review.get("reviewer_role"),
                path="practice_plan.professional_review.reviewer_role",
                issues=issues,
                max_length=120,
            )
            if role.casefold() in MODEL_ROLES or "professional" not in role.casefold():
                _issue(
                    issues,
                    code="invalid_professional_reviewer_role",
                    path="practice_plan.professional_review.reviewer_role",
                    message="reviewed status requires a professional human reviewer role",
                )
            _validate_timestamp(
                professional_review.get("reviewed_at"),
                path="practice_plan.professional_review.reviewed_at",
                issues=issues,
            )
            if review_counts["proposed"] or review_counts["blocked"]:
                _issue(
                    issues,
                    code="reviewed_plan_contains_unresolved_items",
                    path="practice_plan.professional_review.status",
                    message="a reviewed plan cannot contain proposed or blocked items",
                )
    return review_counts


def _update_run_intake(
    output_dir: Path,
    *,
    run_id: str,
    validation_status: str,
    bindings: dict[str, str | None],
) -> None:
    path = output_dir / "run_intake.json"
    if not path.exists():
        return
    payload = load_json_object(path)
    if payload.get("run_id") != run_id or payload.get("plugin") != PLUGIN_NAME:
        raise ValueError("run_intake.json belongs to another run")
    trace = payload.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    trace.append(
        {
            "step_id": f"validate_practice_case_{len(trace) + 1}",
            "kind": "deterministic_validation",
            "command": [
                "python",
                "scripts/validate_practice_case.py",
                "--case-intake",
                "case_intake_draft.json",
                "--practice-plan",
                "practice_plan_draft.json",
                "--official-sources",
                "official_sources.json",
                "--output-dir",
                output_dir.as_posix(),
            ],
            "execution_location": "local_python",
            "status": validation_status,
            "inputs": [
                "case_intake_draft.json",
                "practice_plan_draft.json",
                "official_sources.json",
            ],
            "outputs": ["practice_validation_audit.json"],
            "bindings": bindings,
        }
    )
    payload["execution_trace"] = trace
    payload["status"] = (
        "ready_for_review"
        if validation_status == "passed"
        else "partial" if validation_status == "passed_with_blockers" else "blocked"
    )
    write_private_json(path, payload)


def validate_practice_case(
    case_intake_path: Path,
    practice_plan_path: Path,
    official_sources_path: Path,
    output_dir: Path,
    *,
    local_inventory_path: Path | None = None,
) -> dict[str, Any]:
    """Validate structure, provenance, bindings, and professional-review gates."""

    output_dir = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    issues: list[dict[str, Any]] = []
    intake = load_json_object(case_intake_path)
    plan = load_json_object(practice_plan_path)
    manifest = load_json_object(official_sources_path)
    _walk_privacy(intake, path="case_intake", issues=issues)
    _walk_privacy(plan, path="practice_plan", issues=issues)
    run_id, fact_ids = _validate_case_intake(intake, issues=issues)
    source_ids = _validate_source_manifest(
        manifest, run_id=run_id, output_dir=output_dir, issues=issues
    )
    review_counts = _validate_plan(
        plan,
        run_id=run_id,
        fact_ids=fact_ids,
        source_ids=source_ids,
        issues=issues,
    )
    inventory_hash: str | None = None
    if local_inventory_path is not None:
        inventory = load_json_object(local_inventory_path)
        if inventory.get("plugin") != PLUGIN_NAME or inventory.get("run_id") != run_id:
            _issue(
                issues,
                code="local_inventory_binding_mismatch",
                path="local_evidence_inventory",
                message="local inventory plugin/run id must match the case",
            )
        inventory_hash = sha256_file(local_inventory_path)
        ocr = inventory.get("ocr")
        if isinstance(ocr, dict) and ocr.get("visual_confirmation_required"):
            _issue(
                issues,
                code="ocr_visual_confirmation_required",
                path="local_evidence_inventory.ocr",
                message="OCR text remains partial until a human checks each source image",
                severity="blocker",
            )
    errors = [issue for issue in issues if issue["severity"] == "error"]
    blockers = [issue for issue in issues if issue["severity"] == "blocker"]
    status = (
        "schema_error" if errors else "passed_with_blockers" if blockers else "passed"
    )
    bindings = {
        "case_intake_sha256": sha256_file(case_intake_path),
        "practice_plan_sha256": sha256_file(practice_plan_path),
        "official_sources_sha256": sha256_file(official_sources_path),
        "local_evidence_inventory_sha256": inventory_hash,
    }
    audit = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "workflow": PLUGIN_NAME,
        "run_id": run_id,
        "status": status,
        "semantic_decisions_performed": False,
        "bindings": bindings,
        "source_count": len(source_ids),
        "review_counts": review_counts,
        "error_count": len(errors),
        "blocker_count": len(blockers),
        "issues": issues,
    }
    audit_path = output_dir / "practice_validation_audit.json"
    if not errors:
        validated_intake_path = write_private_json(
            output_dir / "case_intake_validated.json", intake
        )
        validated_plan_path = write_private_json(
            output_dir / "practice_plan_validated.json", plan
        )
        audit["validated_bindings"] = {
            "case_intake_validated_sha256": sha256_file(validated_intake_path),
            "practice_plan_validated_sha256": sha256_file(validated_plan_path),
        }
    write_private_json(audit_path, audit)
    _update_run_intake(
        output_dir,
        run_id=run_id,
        validation_status=status,
        bindings=bindings,
    )
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-intake", type=Path, required=True)
    parser.add_argument("--practice-plan", type=Path, required=True)
    parser.add_argument("--official-sources", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--local-inventory", type=Path)
    args = parser.parse_args(argv)
    try:
        audit = validate_practice_case(
            args.case_intake,
            args.practice_plan,
            args.official_sources,
            args.output_dir,
            local_inventory_path=args.local_inventory,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("VALIDATION_BLOCKED: %s", exc)
        return 2
    LOGGER.info(
        "Validation %s: %s errors, %s blockers",
        audit["status"],
        audit["error_count"],
        audit["blocker_count"],
    )
    return 0 if audit["status"] != "schema_error" else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
