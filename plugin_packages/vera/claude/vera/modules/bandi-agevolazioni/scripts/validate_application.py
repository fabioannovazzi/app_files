"""Validate mechanical integrity of a Bandi e agevolazioni workbench."""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from case_core import (
    PLUGIN_NAME,
    canonical_json_sha256,
    case_lock,
    iso_now,
    load_running_context,
    require_run_artifact,
    safe_identifier,
    write_private_json,
)
from deterministic_rules import RuleContractError, validate_deterministic_rule
from record_review import SCOPES, current_scope_hash
from schema_validation import validate_artifact_schema

__all__ = ["validate_application", "main"]

LOGGER = logging.getLogger(__name__)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
READINESS = {"ready", "missing", "verify", "not_applicable"}
REVIEW_STATUS = {"proposed", "confirmed", "rejected", "blocked"}
PROHIBITED_SECRET_KEYS = {
    "password",
    "passcode",
    "pin",
    "otp",
    "cookie",
    "cookies",
    "token",
    "access_token",
    "refresh_token",
    "session",
    "session_id",
    "signature",
    "spid",
    "cie",
    "cns",
    "credential",
    "credentials",
    "api_key",
    "auth_token",
    "client_secret",
    "digital_signature",
    "one_time_code",
    "private_key",
    "secret_key",
    "session_cookie",
}


def _issue(issues: list[dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _walk_secrets(value: object, *, path: str, issues: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            normalized = re.sub(
                r"[^a-z0-9]+",
                "_",
                str(key).strip().casefold(),
            ).strip("_")
            if normalized in PROHIBITED_SECRET_KEYS:
                _issue(
                    issues,
                    "secret_or_session_material_forbidden",
                    child_path,
                    "credentials, signatures, tokens, cookies, and session material are forbidden",
                )
            _walk_secrets(child, path=child_path, issues=issues)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_secrets(child, path=f"{path}[{index}]", issues=issues)


def _items(
    payload: dict[str, Any], key: str, *, issues: list[dict[str, str]]
) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        _issue(issues, "invalid_collection", key, f"{key} must be a list")
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _issue(
                issues,
                "invalid_item",
                f"{key}[{index}]",
                "item must be an object",
            )
        else:
            items.append(item)
    return items


def _object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object or an empty object after schema issues are recorded."""

    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _has_material_value(value: object) -> bool:
    """Return whether a mechanically required draft value is present."""

    return value is not None and not (isinstance(value, str) and not value.strip())


def _id_set(
    items: Iterable[dict[str, Any]],
    field: str,
    *,
    path: str,
    issues: list[dict[str, str]],
) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(items):
        try:
            identifier = safe_identifier(item.get(field), field=f"{path}.{field}")
        except ValueError as exc:
            _issue(issues, "invalid_id", f"{path}[{index}].{field}", str(exc))
            continue
        if identifier in result:
            _issue(
                issues,
                "duplicate_id",
                f"{path}[{index}].{field}",
                f"duplicate {identifier}",
            )
        result.add(identifier)
    return result


def _check_refs(
    values: object,
    known: set[str],
    *,
    path: str,
    issues: list[dict[str, str]],
    require_one: bool = False,
) -> list[str]:
    if not isinstance(values, list):
        _issue(issues, "invalid_references", path, "references must be a list")
        return []
    refs = [value for value in values if isinstance(value, str)]
    if len(refs) != len(values):
        _issue(issues, "invalid_reference", path, "references must be strings")
    if require_one and not refs:
        _issue(issues, "missing_reference", path, "at least one reference is required")
    if len(refs) != len(set(refs)):
        _issue(issues, "duplicate_reference", path, "references must be unique")
    unknown = sorted(set(refs) - known)
    if unknown:
        _issue(
            issues,
            "unknown_reference",
            path,
            "unknown references: " + ", ".join(unknown),
        )
    return refs


def _review_status(
    item: dict[str, Any], *, path: str, issues: list[dict[str, str]]
) -> str:
    status = str(item.get("review_status") or "")
    if status not in REVIEW_STATUS:
        _issue(issues, "invalid_review_status", path, "invalid review_status")
    return status


def _readiness(item: dict[str, Any], *, path: str, issues: list[dict[str, str]]) -> str:
    readiness = str(item.get("readiness") or "")
    if readiness not in READINESS:
        _issue(issues, "invalid_readiness", path, "invalid readiness")
    if readiness == "ready" and item.get("review_status") != "confirmed":
        _issue(
            issues,
            "ready_requires_confirmed_review",
            path,
            "ready items must be professionally confirmed",
        )
    if readiness == "not_applicable" and not str(item.get("rationale") or "").strip():
        _issue(
            issues,
            "not_applicable_requires_rationale",
            path,
            "not_applicable requires a reviewed rationale",
        )
    if readiness == "not_applicable" and item.get("review_status") != "confirmed":
        _issue(
            issues,
            "not_applicable_requires_confirmed_review",
            path,
            "not_applicable items must be professionally confirmed",
        )
    return readiness


def _latest_review_state(
    output_dir: Path,
    *,
    run_id: str,
    review_log: dict[str, Any],
    issues: list[dict[str, str]],
) -> dict[str, str]:
    events = review_log.get("events")
    if not isinstance(events, list):
        _issue(
            issues, "invalid_review_log", "review_log.events", "events must be a list"
        )
        events = []
    states: dict[str, str] = {}
    for scope in SCOPES:
        expected_hash = current_scope_hash(output_dir, run_id=run_id, scope=scope)
        matching = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("scope") == scope
            and event.get("scope_sha256") == expected_hash
            and event.get("confirmation_basis") == "explicit_user_confirmation"
            and event.get("identity_assurance") == "asserted_not_authenticated"
        ]
        states[scope] = (
            str(matching[-1].get("decision")) if matching else "stale_or_missing"
        )
    return states


def validate_application(
    *, output_dir: Path, client_engagement: Path
) -> dict[str, Any]:
    """Validate contracts and traceability without deciding semantic correctness."""

    context = load_running_context(client_engagement, output_dir=output_dir)
    output_dir = output_dir.resolve()
    with case_lock(output_dir):
        return _validate_application_locked(output_dir=output_dir, context=context)


def _validate_application_locked(
    *, output_dir: Path, context: dict[str, Any]
) -> dict[str, Any]:
    """Validate one immutable case snapshot while cooperative writers are locked."""

    run_id = safe_identifier(context["run_id"], field="run_id")
    intake = require_run_artifact(output_dir / "case_intake.json", run_id=run_id)
    sources = require_run_artifact(output_dir / "source_register.json", run_id=run_id)
    workbench = require_run_artifact(
        output_dir / "application_workbench.json", run_id=run_id
    )
    reviews = require_run_artifact(output_dir / "review_log.json", run_id=run_id)
    run_state = require_run_artifact(output_dir / "run_state.json", run_id=run_id)
    issues: list[dict[str, str]] = []
    for label, payload in (
        ("case_intake", intake),
        ("source_register", sources),
        ("application_workbench", workbench),
        ("review_log", reviews),
        ("run_state", run_state),
    ):
        _walk_secrets(payload, path=label, issues=issues)
        issues.extend(validate_artifact_schema(label, payload))
        if payload.get("plugin") != PLUGIN_NAME or payload.get("run_id") != run_id:
            _issue(issues, "artifact_identity_mismatch", label, "plugin/run mismatch")
    if run_state.get("source_set_revision") != sources.get("source_set_revision"):
        _issue(
            issues,
            "source_set_revision_mismatch",
            "run_state.source_set_revision",
            "run state and source register revisions must match",
        )

    source_items = _items(sources, "sources", issues=issues)
    source_ids = _id_set(source_items, "source_id", path="sources", issues=issues)
    source_by_id = {str(item.get("source_id")): item for item in source_items}
    for index, source in enumerate(source_items):
        if not SHA256_RE.fullmatch(str(source.get("sha256") or "")):
            _issue(
                issues, "invalid_sha256", f"sources[{index}].sha256", "invalid SHA-256"
            )
        relationships = source.get("relationships")
        if not isinstance(relationships, list):
            _issue(
                issues,
                "invalid_relationships",
                f"sources[{index}].relationships",
                "relationships must be a list",
            )
        else:
            normalized_relationships = [
                (
                    item.get("kind"),
                    item.get("target_source_id"),
                )
                for item in relationships
                if isinstance(item, dict)
                and isinstance(item.get("kind"), str)
                and isinstance(item.get("target_source_id"), str)
            ]
            if len(normalized_relationships) != len(set(normalized_relationships)):
                _issue(
                    issues,
                    "duplicate_source_relationship",
                    f"sources[{index}].relationships",
                    "source relationships must be unique",
                )
            if any(
                target_source_id == source.get("source_id")
                for _, target_source_id in normalized_relationships
            ):
                _issue(
                    issues,
                    "self_source_relationship",
                    f"sources[{index}].relationships",
                    "a source cannot relate to itself",
                )
            _check_refs(
                [
                    item.get("target_source_id")
                    for item in relationships
                    if isinstance(item, dict)
                ],
                source_ids,
                path=f"sources[{index}].relationships",
                issues=issues,
            )

    requirements = _items(workbench, "requirements", issues=issues)
    facts = _items(workbench, "facts", issues=issues)
    assessments = _items(workbench, "assessments", issues=issues)
    documents = _items(workbench, "document_checklist", issues=issues)
    expenses = _items(workbench, "expenses", issues=issues)
    form_fields = _items(workbench, "form_fields", issues=issues)
    narratives = _items(workbench, "narratives", issues=issues)
    consistency_checks = _items(workbench, "consistency_checks", issues=issues)
    issue_items = _items(workbench, "issues", issues=issues)
    requirement_ids = _id_set(
        requirements, "requirement_id", path="requirements", issues=issues
    )
    fact_ids = _id_set(facts, "fact_id", path="facts", issues=issues)
    assessment_ids = _id_set(
        assessments, "assessment_id", path="assessments", issues=issues
    )
    document_ids = _id_set(
        documents, "document_id", path="document_checklist", issues=issues
    )
    expense_ids = _id_set(expenses, "expense_id", path="expenses", issues=issues)
    form_field_ids = _id_set(form_fields, "field_id", path="form_fields", issues=issues)
    narrative_ids = _id_set(
        narratives, "narrative_id", path="narratives", issues=issues
    )
    consistency_check_ids = _id_set(
        consistency_checks,
        "check_id",
        path="consistency_checks",
        issues=issues,
    )
    issue_ids = _id_set(issue_items, "issue_id", path="issues", issues=issues)
    fact_by_id = {str(item.get("fact_id")): item for item in facts}

    for index, requirement in enumerate(requirements):
        path = f"requirements[{index}]"
        _review_status(requirement, path=path, issues=issues)
        refs = requirement.get("source_refs")
        if not isinstance(refs, list) or not refs:
            _issue(
                issues,
                "requirement_missing_source",
                f"{path}.source_refs",
                "requirements need at least one exact source fragment",
            )
            continue
        for ref_index, ref in enumerate(refs):
            ref_path = f"{path}.source_refs[{ref_index}]"
            if not isinstance(ref, dict):
                _issue(
                    issues,
                    "invalid_source_ref",
                    ref_path,
                    "source ref must be an object",
                )
                continue
            source_id = str(ref.get("source_id") or "")
            if source_id not in source_ids:
                _issue(
                    issues,
                    "unknown_reference",
                    f"{ref_path}.source_id",
                    f"unknown source {source_id}",
                )
            if not str(ref.get("locator") or "").strip():
                _issue(
                    issues,
                    "missing_locator",
                    f"{ref_path}.locator",
                    "source locator is required",
                )
            if not SHA256_RE.fullmatch(str(ref.get("excerpt_sha256") or "")):
                _issue(
                    issues,
                    "invalid_excerpt_sha256",
                    f"{ref_path}.excerpt_sha256",
                    "invalid excerpt SHA-256",
                )
            excerpt = ref.get("excerpt")
            if isinstance(excerpt, str) and excerpt:
                expected_excerpt_hash = hashlib.sha256(
                    excerpt.encode("utf-8")
                ).hexdigest()
                if ref.get("excerpt_sha256") != expected_excerpt_hash:
                    _issue(
                        issues,
                        "excerpt_sha256_mismatch",
                        f"{ref_path}.excerpt_sha256",
                        "excerpt_sha256 must hash the exact stored UTF-8 excerpt",
                    )
            if (
                requirement.get("review_status") == "confirmed"
                and source_by_id.get(source_id, {}).get("review_status") != "reviewed"
            ):
                _issue(
                    issues,
                    "confirmed_requirement_uses_unreviewed_source",
                    ref_path,
                    "confirmed requirements require reviewed sources",
                )

    for index, fact in enumerate(facts):
        _review_status(fact, path=f"facts[{index}]", issues=issues)
        _check_refs(
            fact.get("source_ids"),
            source_ids,
            path=f"facts[{index}].source_ids",
            issues=issues,
        )

    negative_assessment = False
    for index, assessment in enumerate(assessments):
        path = f"assessments[{index}]"
        _review_status(assessment, path=path, issues=issues)
        _readiness(assessment, path=path, issues=issues)
        _check_refs(
            [assessment.get("requirement_id")],
            requirement_ids,
            path=f"{path}.requirement_id",
            issues=issues,
            require_one=True,
        )
        fact_refs = _check_refs(
            assessment.get("fact_ids"), fact_ids, path=f"{path}.fact_ids", issues=issues
        )
        outcome = assessment.get("outcome")
        negative_assessment = negative_assessment or outcome == "not_satisfied"
        if (
            assessment.get("readiness") == "not_applicable"
            and outcome != "not_applicable"
        ):
            _issue(
                issues,
                "not_applicable_outcome_mismatch",
                path,
                "not_applicable readiness requires not_applicable outcome",
            )
        if assessment.get("readiness") == "ready" and outcome != "not_applicable":
            if not fact_refs:
                _issue(
                    issues,
                    "ready_assessment_requires_fact",
                    f"{path}.fact_ids",
                    "a ready applicable assessment requires at least one reviewed fact",
                )
            unconfirmed = [
                fact_id
                for fact_id in fact_refs
                if fact_by_id.get(fact_id, {}).get("review_status") != "confirmed"
            ]
            if unconfirmed:
                _issue(
                    issues,
                    "ready_assessment_uses_unconfirmed_fact",
                    f"{path}.fact_ids",
                    "ready assessments require confirmed facts: "
                    + ", ".join(sorted(unconfirmed)),
                )
        evaluation_method = assessment.get("evaluation_method")
        rule = assessment.get("deterministic_rule")
        if evaluation_method == "model_led" and rule is not None:
            _issue(
                issues,
                "model_led_assessment_has_deterministic_rule",
                f"{path}.deterministic_rule",
                "model-led assessments cannot claim a deterministic rule",
            )
        if evaluation_method in {"deterministic", "hybrid"}:
            try:
                validate_deterministic_rule(rule, assessment_outcome=outcome)
            except RuleContractError as exc:
                _issue(
                    issues,
                    "deterministic_rule_not_reproducible",
                    f"{path}.deterministic_rule",
                    str(exc),
                )

    for key, items in (
        ("document_checklist", documents),
        ("expenses", expenses),
        ("form_fields", form_fields),
        ("narratives", narratives),
    ):
        for index, item in enumerate(items):
            path = f"{key}[{index}]"
            _review_status(item, path=path, issues=issues)
            _readiness(item, path=path, issues=issues)
            requirement_refs = _check_refs(
                item.get("requirement_ids"),
                requirement_ids,
                path=f"{path}.requirement_ids",
                issues=issues,
            )
            if key in {"document_checklist", "expenses"}:
                source_field = (
                    "material_source_ids"
                    if key == "document_checklist"
                    else "source_ids"
                )
                source_refs = _check_refs(
                    item.get(source_field),
                    source_ids,
                    path=f"{path}.{source_field}",
                    issues=issues,
                )
                if item.get("readiness") == "ready" and (
                    not requirement_refs or not source_refs
                ):
                    _issue(
                        issues,
                        "ready_item_missing_traceability",
                        path,
                        "ready documents and expenses require requirement and source links",
                    )
            if key in {"form_fields", "narratives"}:
                fact_refs = _check_refs(
                    item.get("fact_ids"),
                    fact_ids,
                    path=f"{path}.fact_ids",
                    issues=issues,
                )
            if key == "form_fields":
                protected = any(
                    bool(item.get(field))
                    for field in (
                        "declaration_control",
                        "signature_control",
                        "submission_control",
                    )
                )
                if protected and not item.get("manual_only"):
                    _issue(
                        issues,
                        "protected_field_must_be_manual",
                        path,
                        "declaration, signature, and submission controls must be manual_only",
                    )
                if protected and item.get("proposed_value") not in (None, ""):
                    _issue(
                        issues,
                        "protected_field_must_be_empty",
                        path,
                        "protected controls cannot have a proposed value",
                    )
                if (
                    item.get("readiness") == "ready"
                    and not protected
                    and (not requirement_refs or not fact_refs)
                ):
                    _issue(
                        issues,
                        "ready_item_missing_traceability",
                        path,
                        "ready ordinary form fields require requirement and fact links",
                    )
                if (
                    item.get("readiness") == "ready"
                    and not protected
                    and not _has_material_value(item.get("proposed_value"))
                ):
                    _issue(
                        issues,
                        "ready_form_field_missing_value",
                        f"{path}.proposed_value",
                        "ready ordinary form fields require a proposed value",
                    )
            if (
                key == "narratives"
                and item.get("readiness") == "ready"
                and (not requirement_refs or not fact_refs)
            ):
                _issue(
                    issues,
                    "ready_item_missing_traceability",
                    path,
                    "ready narratives require requirement and fact links",
                )
            if (
                key == "narratives"
                and item.get("readiness") == "ready"
                and not str(item.get("draft") or "").strip()
            ):
                _issue(
                    issues,
                    "ready_narrative_missing_draft",
                    f"{path}.draft",
                    "ready narratives require a non-empty draft",
                )
            if (
                key == "expenses"
                and item.get("readiness") == "not_applicable"
                and item.get("outcome") != "not_assessed"
            ):
                _issue(
                    issues,
                    "expense_not_applicable_outcome_mismatch",
                    path,
                    "not_applicable expenses require outcome not_assessed",
                )

    consistency_conflict = False
    for index, item in enumerate(consistency_checks):
        path = f"consistency_checks[{index}]"
        _review_status(item, path=path, issues=issues)
        consistency_fact_refs = _check_refs(
            item.get("fact_ids"),
            fact_ids,
            path=f"{path}.fact_ids",
            issues=issues,
        )
        consistency_source_refs = _check_refs(
            item.get("source_ids"),
            source_ids,
            path=f"{path}.source_ids",
            issues=issues,
        )
        if (
            item.get("outcome") == "consistent"
            and item.get("review_status") == "confirmed"
            and len(set(consistency_fact_refs + consistency_source_refs)) < 2
        ):
            _issue(
                issues,
                "consistency_check_missing_evidence",
                path,
                "a confirmed consistency check requires at least two evidence links",
            )
        outcome = item.get("outcome")
        consistency_conflict = consistency_conflict or outcome == "conflict"
        if outcome == "not_applicable":
            _readiness(
                {
                    "readiness": "not_applicable",
                    "rationale": item.get("rationale"),
                    "review_status": item.get("review_status"),
                },
                path=path,
                issues=issues,
            )

    related_ids = (
        source_ids
        | requirement_ids
        | fact_ids
        | assessment_ids
        | document_ids
        | expense_ids
        | form_field_ids
        | narrative_ids
        | consistency_check_ids
        | issue_ids
    )
    authority = workbench.get("authority_simulation")
    authority_checks: list[dict[str, Any]] = []
    if not isinstance(authority, dict):
        _issue(
            issues,
            "invalid_authority_simulation",
            "authority_simulation",
            "authority_simulation must be an object",
        )
        authority = {}
    else:
        authority_checks = _items(authority, "checks", issues=issues)
    authority_check_ids = _id_set(
        authority_checks,
        "check_id",
        path="authority_simulation.checks",
        issues=issues,
    )
    # IDs form one global namespace because issue and authority links carry no
    # type discriminator. Global uniqueness makes every reference auditable.
    id_collections = (
        ("source", source_ids),
        ("requirement", requirement_ids),
        ("fact", fact_ids),
        ("assessment", assessment_ids),
        ("document", document_ids),
        ("expense", expense_ids),
        ("form_field", form_field_ids),
        ("narrative", narrative_ids),
        ("consistency_check", consistency_check_ids),
        ("issue", issue_ids),
        ("authority_check", authority_check_ids),
    )
    owners: dict[str, str] = {}
    for kind, identifiers in id_collections:
        for identifier in identifiers:
            if identifier in owners:
                _issue(
                    issues,
                    "cross_type_duplicate_id",
                    kind,
                    f"{identifier} is already used as {owners[identifier]}",
                )
            else:
                owners[identifier] = kind
    for index, item in enumerate(authority_checks):
        path = f"authority_simulation.checks[{index}]"
        _review_status(item, path=path, issues=issues)
        _check_refs(
            item.get("related_ids"),
            related_ids,
            path=f"{path}.related_ids",
            issues=issues,
        )
        if item.get("outcome") == "not_applicable":
            _readiness(
                {
                    "readiness": "not_applicable",
                    "rationale": item.get("rationale"),
                    "review_status": item.get("review_status"),
                },
                path=path,
                issues=issues,
            )

    open_blockers = [
        item
        for item in issue_items
        if item.get("severity") in {"blocking", "review_required"}
        and item.get("status") == "open"
    ]
    for index, item in enumerate(issue_items):
        _review_status(item, path=f"issues[{index}]", issues=issues)
        _check_refs(
            item.get("related_ids"),
            related_ids,
            path=f"issues[{index}].related_ids",
            issues=issues,
        )
        if (
            item.get("severity") in {"blocking", "review_required"}
            and item.get("status") != "open"
            and item.get("review_status") != "confirmed"
        ):
            _issue(
                issues,
                "material_issue_closure_requires_confirmed_review",
                f"issues[{index}]",
                "closing a material issue requires confirmed professional review",
            )

    dossier = workbench.get("dossier")
    if not isinstance(dossier, dict):
        _issue(issues, "invalid_dossier", "dossier", "dossier must be an object")
        dossier = {}
    if dossier.get("ready_to_file") is not False:
        _issue(
            issues,
            "ready_to_file_forbidden",
            "dossier.ready_to_file",
            "ready_to_file must remain false",
        )
    review_states = _latest_review_state(
        output_dir,
        run_id=run_id,
        review_log=reviews,
        issues=issues,
    )
    disposition = dossier.get("disposition")
    all_readiness = [
        item.get("readiness")
        for collection in (assessments, documents, expenses, form_fields, narratives)
        for item in collection
    ]
    if disposition == "ready_for_authorized_review":
        application = _object(intake, "application")
        applicant = _object(intake, "applicant")
        project = _object(intake, "project")
        required_nonempty = {
            "sources": source_items,
            "requirements": requirements,
            "assessments": assessments,
            "document_checklist": documents,
            "expenses": expenses,
            "form_fields": form_fields,
            "narratives": narratives,
            "consistency_checks": consistency_checks,
            "authority_simulation.checks": authority_checks,
        }
        empty = sorted(name for name, items in required_nonempty.items() if not items)
        if empty:
            _issue(
                issues,
                "ready_disposition_incomplete_dossier",
                "dossier.disposition",
                "ready disposition requires non-empty reviewed sections: "
                + ", ".join(empty),
            )
        intake_checks = {
            "application.status": application.get("status"),
            "applicant.confirmation_status": applicant.get("confirmation_status"),
            "project.confirmation_status": project.get("confirmation_status"),
        }
        unconfirmed_intake = sorted(
            field for field, value in intake_checks.items() if value != "confirmed"
        )
        required_text = {
            "application.title": application.get("title"),
            "application.issuing_authority": application.get("issuing_authority"),
            "application.procedure_id": application.get("procedure_id"),
            "applicant.legal_name": applicant.get("legal_name"),
            "project.title": project.get("title"),
            "project.summary": project.get("summary"),
            "professional_question": intake.get("professional_question"),
            "workbench.case_summary": workbench.get("case_summary"),
        }
        unconfirmed_intake.extend(
            field
            for field, value in required_text.items()
            if not str(value or "").strip()
        )
        if unconfirmed_intake:
            _issue(
                issues,
                "ready_disposition_has_unconfirmed_intake",
                "case_intake",
                "ready disposition requires confirmed material intake: "
                + ", ".join(sorted(set(unconfirmed_intake))),
            )
        if any(source.get("review_status") != "reviewed" for source in source_items):
            _issue(
                issues,
                "ready_disposition_has_unreviewed_sources",
                "source_register.sources",
                "every source in a ready dossier must be reviewed",
            )
        governing_calls = [
            source
            for source in source_items
            if source.get("source_type") == "call"
            and source.get("review_status") == "reviewed"
        ]
        if not governing_calls:
            _issue(
                issues,
                "ready_disposition_missing_governing_call",
                "source_register.sources",
                "ready disposition requires at least one reviewed governing call",
            )
        formal_source_types = {"call", "formal_amendment", "official_faq"}
        undated_official_sources = sorted(
            str(source.get("source_id"))
            for source in source_items
            if source.get("source_type") in formal_source_types
            and (
                source.get("publication_date") is None
                or source.get("effective_from") is None
            )
        )
        if undated_official_sources:
            _issue(
                issues,
                "ready_disposition_has_undated_official_sources",
                "source_register.sources",
                "publication_date and effective_from are required for: "
                + ", ".join(undated_official_sources),
            )
        relationship_gaps: list[str] = []
        for source in source_items:
            source_type = source.get("source_type")
            expected_kinds = (
                {"clarifies"}
                if source_type == "official_faq"
                else (
                    {"amends", "supersedes"}
                    if source_type == "formal_amendment"
                    else set()
                )
            )
            if not expected_kinds:
                continue
            valid_relationship = any(
                isinstance(relationship, dict)
                and relationship.get("kind") in expected_kinds
                and source_by_id.get(str(relationship.get("target_source_id")), {}).get(
                    "source_type"
                )
                in {"call", "formal_amendment"}
                for relationship in source.get("relationships", [])
            )
            if not valid_relationship:
                relationship_gaps.append(str(source.get("source_id")))
        if relationship_gaps:
            _issue(
                issues,
                "ready_disposition_has_unbound_dependent_sources",
                "source_register.sources",
                "FAQ and amendment sources require explicit formal-source relationships: "
                + ", ".join(sorted(relationship_gaps)),
            )
        if any(
            requirement.get("review_status") != "confirmed"
            for requirement in requirements
        ):
            _issue(
                issues,
                "ready_disposition_has_unconfirmed_requirements",
                "requirements",
                "every requirement in a ready dossier must be confirmed",
            )
        if any(fact.get("review_status") != "confirmed" for fact in facts):
            _issue(
                issues,
                "ready_disposition_has_unconfirmed_facts",
                "facts",
                "every fact in a ready dossier must be confirmed",
            )
        empty_fact_ids = sorted(
            str(fact.get("fact_id"))
            for fact in facts
            if not _has_material_value(fact.get("value"))
        )
        if empty_fact_ids:
            _issue(
                issues,
                "ready_disposition_has_empty_facts",
                "facts",
                "ready disposition requires material fact values: "
                + ", ".join(empty_fact_ids),
            )
        assessed_requirement_ids = [
            str(assessment.get("requirement_id")) for assessment in assessments
        ]
        missing_assessments = sorted(requirement_ids - set(assessed_requirement_ids))
        duplicate_assessments = sorted(
            requirement_id
            for requirement_id in set(assessed_requirement_ids)
            if assessed_requirement_ids.count(requirement_id) > 1
        )
        if missing_assessments or duplicate_assessments:
            _issue(
                issues,
                "ready_disposition_has_assessment_coverage_gap",
                "assessments",
                "one assessment is required per requirement; missing="
                + ",".join(missing_assessments)
                + "; duplicate="
                + ",".join(duplicate_assessments),
            )
        if any(value in {"missing", "verify"} for value in all_readiness):
            _issue(
                issues,
                "ready_disposition_has_unresolved_items",
                "dossier.disposition",
                "ready disposition cannot contain missing or verify items",
            )
        unresolved_outcomes = [
            str(item.get("assessment_id"))
            for item in assessments
            if item.get("outcome") not in {"satisfied", "not_applicable"}
        ]
        unresolved_consistency = [
            str(item.get("check_id"))
            for item in consistency_checks
            if item.get("outcome") not in {"consistent", "not_applicable"}
            or item.get("review_status") != "confirmed"
        ]
        unresolved_authority = [
            str(item.get("check_id"))
            for item in authority_checks
            if item.get("outcome") not in {"pass", "not_applicable"}
            or item.get("review_status") != "confirmed"
        ]
        authority_covered_ids = {
            related_id
            for item in authority_checks
            for related_id in item.get("related_ids", [])
            if isinstance(related_id, str)
        }
        material_ids = (
            requirement_ids
            | fact_ids
            | assessment_ids
            | document_ids
            | expense_ids
            | form_field_ids
            | narrative_ids
            | consistency_check_ids
            | {
                str(item.get("issue_id"))
                for item in issue_items
                if item.get("severity") in {"blocking", "review_required"}
            }
        )
        missing_authority_coverage = sorted(material_ids - authority_covered_ids)
        if missing_authority_coverage:
            _issue(
                issues,
                "authority_simulation_coverage_gap",
                "authority_simulation.checks",
                "authority simulation does not cover: "
                + ", ".join(missing_authority_coverage),
            )
        if (
            authority.get("status") != "reviewed"
            or authority.get("overall_outcome") != "pass"
            or unresolved_authority
        ):
            _issue(
                issues,
                "ready_disposition_has_unreviewed_authority_simulation",
                "authority_simulation",
                "ready disposition requires a reviewed passing authority simulation",
            )
        if unresolved_consistency or consistency_conflict:
            _issue(
                issues,
                "ready_disposition_has_unresolved_consistency",
                "consistency_checks",
                "ready disposition requires confirmed consistent checks",
            )
        if negative_assessment or unresolved_outcomes or open_blockers:
            _issue(
                issues,
                "ready_disposition_has_adverse_result",
                "dossier.disposition",
                "ready disposition cannot contain unresolved assessments or open review issues",
            )
        adverse_expenses = [
            str(item.get("expense_id"))
            for item in expenses
            if item.get("readiness") == "ready" and item.get("outcome") != "eligible"
        ]
        if adverse_expenses:
            _issue(
                issues,
                "ready_disposition_has_adverse_expenses",
                "expenses",
                "ready disposition requires eligible expense outcomes: "
                + ", ".join(adverse_expenses),
            )
        stale = [
            scope for scope, decision in review_states.items() if decision != "accepted"
        ]
        if stale:
            _issue(
                issues,
                "ready_disposition_has_stale_reviews",
                "dossier.disposition",
                "accepted current reviews required: " + ", ".join(stale),
            )
    if disposition == "not_eligible_or_excluded":
        if not negative_assessment:
            _issue(
                issues,
                "negative_disposition_without_negative_assessment",
                "dossier.disposition",
                "negative disposition requires a not_satisfied assessment",
            )
        if review_states.get("assessments") != "accepted":
            _issue(
                issues,
                "negative_disposition_requires_review",
                "dossier.disposition",
                "negative disposition requires accepted current assessment review",
            )

    artifact_hashes = {
        "case_intake": canonical_json_sha256(intake),
        "source_register": canonical_json_sha256(sources),
        "application_workbench": canonical_json_sha256(workbench),
        "review_log": canonical_json_sha256(reviews),
        "run_state": canonical_json_sha256(run_state),
    }
    audit = {
        "schema_version": "1.1",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "validated_at": iso_now(),
        "status": "passed" if not issues else "failed",
        "ready_to_file": False,
        "portal_actions_performed": run_state.get("portal_actions_performed"),
        "signature_actions_performed": run_state.get("signature_actions_performed"),
        "submission_actions_performed": run_state.get("submission_actions_performed"),
        "artifact_hashes": artifact_hashes,
        "review_states": review_states,
        "counts": {
            "sources": len(source_items),
            "requirements": len(requirements),
            "facts": len(facts),
            "assessments": len(assessments),
            "documents": len(documents),
            "expenses": len(expenses),
            "form_fields": len(form_fields),
            "narratives": len(narratives),
            "consistency_checks": len(consistency_checks),
            "authority_checks": len(authority_checks),
            "issues": len(issue_items),
        },
        "issues": issues,
        "limitations": [
            "Mechanical validation does not establish source authority, legal interpretation, eligibility, cost admissibility, or filing readiness."
        ],
    }
    write_private_json(output_dir / "validation_audit.json", audit)
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    audit = validate_application(
        output_dir=args.output_dir,
        client_engagement=args.client_engagement,
    )
    LOGGER.info("Validation: %s (%s issues)", audit["status"], len(audit["issues"]))
    return 0 if audit["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
