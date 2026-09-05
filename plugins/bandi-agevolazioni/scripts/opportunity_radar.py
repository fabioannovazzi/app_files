"""Operate Vera's private, reviewable grant-opportunity radar workbench."""

from __future__ import annotations

import argparse
import logging
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from case_core import (
    PLUGIN_NAME,
    canonical_json_sha256,
    case_lock,
    iso_now,
    load_json_object,
    prohibited_secret_paths,
    prohibited_secret_value_paths,
    safe_identifier,
    validate_iso_date,
    write_private_json,
    write_private_text,
)
from schema_validation import validate_artifact_schema

__all__ = [
    "create_handoff",
    "initialize_radar",
    "load_validated_radar",
    "record_match",
    "record_opportunity",
    "record_profile_evidence",
    "record_profile",
    "record_scan",
    "record_source",
    "record_source_check",
    "render_radar_report",
    "render_scan_worklist",
    "review_item",
    "validate_opportunity_handoff_payload",
    "main",
]

LOGGER = logging.getLogger(__name__)
RADAR_FILENAME = "opportunity_radar.json"
REVIEW_SCOPES = {
    "evidence": ("profile_evidence", "evidence_id"),
    "profile": ("profiles", "client_ref"),
    "source": ("source_plan", "source_id"),
    "source_check": ("source_plan", "source_id"),
    "scan_source_selection": ("monitoring", "scan_id"),
    "opportunity": ("opportunities", "opportunity_id"),
    "match": ("matches", "match_id"),
}
DECISIONS = {"accepted", "returned", "rejected"}
CHECK_STATUSES = {"planned", "checked", "unavailable", "failed", "not_applicable"}
DISCOVERY_ROLES = {"priority_direct", "supplemental_direct"}
SEMANTIC_WEB_STATUSES = {"not_run", "checked", "unavailable", "failed"}
QUERY_SCOPE_FIELDS = {"territory": "territories", "category": "categories"}


def _radar_path(workspace: Path) -> Path:
    expanded = workspace.expanduser()
    if not expanded.is_absolute():
        raise ValueError("radar workspace must be an absolute path")
    unresolved = expanded.absolute()
    for candidate in (unresolved, *unresolved.parents):
        if candidate.exists() and candidate.is_symlink():
            raise PermissionError("radar workspace cannot traverse a symbolic link")
        if (candidate / ".git").exists():
            raise PermissionError("radar workspace cannot be inside a Git worktree")
    resolved = unresolved.resolve()
    lowered_parts = tuple(part.casefold() for part in resolved.parts)
    if "protected_downloads" in lowered_parts or any(
        lowered_parts[index : index + 2] == ("static", "shared")
        for index in range(max(0, len(lowered_parts) - 1))
    ):
        raise PermissionError("radar workspace cannot be inside a published folder")
    if resolved in {Path(resolved.anchor), Path.home().resolve()}:
        raise PermissionError("radar workspace is too broad")
    resolved.mkdir(parents=True, mode=0o700, exist_ok=True)
    resolved.chmod(0o700)
    return resolved / RADAR_FILENAME


def _workspace_sha256(workspace: Path) -> str:
    """Bind a private radar to one exact local directory for audit safety."""

    return canonical_json_sha256(str(_radar_path(workspace).parent))


def _datetime(value: object, *, field: str) -> datetime:
    """Parse a schema-validated ISO timestamp for mechanical ordering checks."""

    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal string") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal string")
    return number


def _contribution(
    *,
    origin: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    model_session_ref: str | None = None,
) -> dict[str, str | None]:
    normalized_session_ref: str | None = None
    if model_session_ref is not None:
        normalized_session_ref = safe_identifier(
            model_session_ref, field="model_session_ref"
        )
        if len(normalized_session_ref) < 8:
            raise ValueError("model_session_ref must contain at least 8 characters")
    if (
        origin in {"model_suggested", "document_observation"}
        and not normalized_session_ref
    ):
        raise ValueError(
            "model_session_ref is required for model or document-observation contributions"
        )
    return {
        "origin": origin,
        "provider": str(provider).strip(),
        "model": str(model).strip(),
        "prompt_template_version": str(prompt_template_version).strip(),
        "recorded_by": safe_identifier(recorded_by, field="recorded_by"),
        "recorded_at": iso_now(),
        "model_session_ref": normalized_session_ref,
        "session_assurance": (
            "operator_asserted_not_provider_authenticated"
            if normalized_session_ref
            else "not_applicable"
        ),
    }


def _reject_unmistakable_secret_values(value: object, *, label: str) -> None:
    paths = prohibited_secret_value_paths(value, path=label)
    if paths:
        raise ValueError(
            f"{label} contains unmistakable credential/session material at: "
            + ", ".join(paths)
        )


def _assert_client_mapping_session_isolated(
    radar: Mapping[str, Any], *, client_ref: str, model_session_ref: str | None
) -> None:
    if model_session_ref is None:
        return
    for collection in ("profile_evidence", "profiles"):
        for item in radar.get(collection, []):
            contribution = item.get("contribution", {})
            if (
                contribution.get("model_session_ref") == model_session_ref
                and item.get("client_ref") != client_ref
            ):
                raise ValueError(
                    "one client-evidence mapping session cannot be reused for another client"
                )
    if any(
        contribution.get("model_session_ref") == model_session_ref
        for contribution in _non_mapping_contributions(radar)
    ):
        raise ValueError(
            "client-evidence mapping requires a session separate from public "
            "discovery and portfolio matching"
        )


def _non_mapping_contributions(
    radar: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    contributions: list[Mapping[str, Any]] = []
    for item in radar.get("source_plan", {}).get("entries", []):
        contribution = item.get("contribution", {})
        if isinstance(contribution, Mapping):
            contributions.append(contribution)
    for collection in ("opportunities", "matches"):
        for item in radar.get(collection, []):
            contribution = item.get("contribution", {})
            if isinstance(contribution, Mapping):
                contributions.append(contribution)
    for scan in radar.get("monitoring", {}).get("scan_history", []):
        contribution = scan.get("source_selection", {}).get("contribution", {})
        if isinstance(contribution, Mapping):
            contributions.append(contribution)
    return contributions


def _assert_non_mapping_session_isolated(
    radar: Mapping[str, Any], *, model_session_ref: str | None
) -> None:
    if model_session_ref is None:
        return
    if any(
        item.get("contribution", {}).get("model_session_ref") == model_session_ref
        for collection in ("profile_evidence", "profiles")
        for item in radar.get(collection, [])
    ):
        raise ValueError(
            "public discovery and portfolio matching require a session separate "
            "from client-evidence mapping"
        )


def _find(items: list[dict[str, Any]], field: str, value: str) -> dict[str, Any]:
    for item in items:
        if item.get(field) == value:
            return item
    raise ValueError(f"unknown {field}: {value}")


def _unique_ids(items: list[dict[str, Any]], field: str) -> set[str]:
    values = [safe_identifier(item.get(field), field=field) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field}")
    return set(values)


def _coverage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    # Only professionally confirmed plan entries belong to the reviewed-plan
    # denominator; this is a closed, mechanically reproducible audit fact.
    reviewed = [item for item in entries if item.get("review_status") == "confirmed"]
    eligible = [
        item
        for item in reviewed
        if not (
            item.get("check_status") == "not_applicable"
            and item.get("check_review_status") == "confirmed"
        )
    ]
    planned_count = len(eligible)
    completed_count = sum(
        item.get("check_status") == "checked"
        and item.get("check_review_status") == "confirmed"
        for item in eligible
    )
    unavailable_count = sum(
        item.get("check_status") == "unavailable"
        and item.get("check_review_status") == "confirmed"
        for item in eligible
    )
    failed_count = sum(
        item.get("check_status") == "failed"
        and item.get("check_review_status") == "confirmed"
        for item in eligible
    )
    pending_count = sum(
        item.get("review_status") in {"proposed", "blocked"} for item in entries
    )
    rejected_count = sum(item.get("review_status") == "rejected" for item in entries)
    check_review_pending_count = sum(
        item.get("check_status") != "planned"
        and item.get("check_review_status") != "confirmed"
        for item in eligible
    )
    ratio = 0 if planned_count == 0 else completed_count * 10_000 // planned_count
    if pending_count:
        status = "plan_unreviewed"
    elif completed_count == 0:
        status = "not_started"
    elif completed_count == planned_count and check_review_pending_count == 0:
        status = "planned_sources_checked"
    else:
        status = "partial"
    return {
        "plan_entry_count": len(entries),
        "planned_count": planned_count,
        "completed_count": completed_count,
        "unavailable_count": unavailable_count,
        "failed_count": failed_count,
        "unreviewed_count": pending_count,
        "rejected_count": rejected_count,
        "check_review_pending_count": check_review_pending_count,
        "ratio_basis_points": ratio,
        "status": status,
        "statement": (
            f"{completed_count}/{planned_count} professionally confirmed applicable plan sources checked and review-confirmed; "
            f"{pending_count} pending plan entries and {rejected_count} rejected entries excluded; "
            "this measures execution of the reviewed plan, not the probability that all opportunities were found."
        ),
    }


def _source_registry_basis(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return reviewed source metadata, excluding mutable check state."""

    fields = (
        "source_id",
        "authority_level",
        "publisher",
        "official_url",
        "discovery_role",
        "source_surface",
        "territories",
        "categories",
        "act_families",
        "relevance_rationale",
        "profile_refs",
        "contribution",
    )
    return {field: entry[field] for field in fields}


def _source_registry_sha256(entries: list[dict[str, Any]]) -> str:
    """Seal the exact reviewed registry used to start one scan."""

    return canonical_json_sha256(
        [
            _source_registry_basis(item)
            for item in sorted(entries, key=lambda value: value["source_id"])
        ]
    )


def _source_check_snapshot(entry: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "source_id",
        "check_id",
        "last_scan_id",
        "check_status",
        "checked_at",
        "window_start",
        "window_end",
        "result_count",
        "error_code",
        "cursor_before",
        "cursor_after",
        "check_review_status",
    )
    return {
        **{field: deepcopy(entry[field]) for field in fields},
        "issue_inventory": deepcopy(entry.get("issue_inventory")),
    }


def _validate_issue_inventory(entry: Mapping[str, Any]) -> None:
    """Check declared issue coverage mechanically; relevance remains model-led."""

    inventory = entry.get("issue_inventory")
    if inventory is None:
        if (
            entry.get("source_surface") == "official_gazette"
            and entry["check_status"] == "checked"
        ):
            raise ValueError("checked gazette requires an issue inventory")
        return
    if (
        inventory["window_start"] > entry["window_start"]
        or inventory["window_end"] < entry["window_end"]
    ):
        raise ValueError("issue inventory does not cover the source check window")
    if inventory["window_start"] > inventory["window_end"]:
        raise ValueError("issue inventory window ends before it starts")
    if _datetime(inventory["enumerated_at"], field="enumerated_at") > _datetime(
        entry["checked_at"], field="checked_at"
    ):
        raise ValueError("issue inventory cannot be enumerated after its check")
    issues = inventory["issues"]
    _unique_ids(issues, "issue_id")
    for issue in issues:
        if (
            not inventory["window_start"]
            <= issue["publication_date"]
            <= inventory["window_end"]
        ):
            raise ValueError("issue publication date is outside inventory window")
        if issue["checked_at"] is not None and _datetime(
            issue["checked_at"], field="issue checked_at"
        ) > _datetime(entry["checked_at"], field="checked_at"):
            raise ValueError("issue inspection cannot follow its source check")
    if entry["check_status"] == "checked":
        if not inventory["enumeration_complete"] or any(
            issue["status"] != "checked" for issue in issues
        ):
            raise ValueError("checked gazette requires complete issue coverage")
        if not issues and not inventory["empty_window_rationale"].strip():
            raise ValueError("empty gazette inventory requires an evidenced rationale")


def _selection_source_ids(selection: Mapping[str, Any]) -> set[str]:
    """Return the exact query-scoped source set proposed for one scan."""

    return set(selection["priority_source_ids"]) | set(
        selection["supplemental_source_ids"]
    )


def _source_selection_proposal_basis(
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    """Return caller-supplied semantic selection fields without review metadata."""

    fields = (
        "priority_source_ids",
        "supplemental_source_ids",
        "scope_coverage",
        "selection_rationale",
    )
    return {field: deepcopy(selection[field]) for field in fields}


def _scope_gap_keys(selection: Mapping[str, Any]) -> list[str]:
    """Return mechanically declared query dimensions without source coverage."""

    return sorted(
        f"{claim['dimension']}:{claim['query_value']}"
        for claim in selection["scope_coverage"]
        if claim["status"] == "gap"
    )


def _validate_scan_source_selection(
    *,
    selection: Mapping[str, Any],
    query_context: Mapping[str, Any],
    entries: list[dict[str, Any]],
    require_confirmed_sources: bool,
) -> None:
    """Validate a reviewed semantic selection without inferring source relevance.

    Exact query-dimension coverage and reference closure are deterministic
    because they are closed audit contracts. The model and professional still
    decide which sources cover each territory or category and why.
    """

    required_fields = {
        "priority_source_ids",
        "supplemental_source_ids",
        "scope_coverage",
        "selection_rationale",
    }
    missing_fields = sorted(required_fields - set(selection))
    if missing_fields:
        raise ValueError(
            "scan source selection is missing required fields: "
            + ", ".join(missing_fields)
        )
    missing_query_fields = sorted(
        field for field in QUERY_SCOPE_FIELDS.values() if field not in query_context
    )
    if missing_query_fields:
        raise ValueError(
            "scan query context is missing required fields: "
            + ", ".join(missing_query_fields)
        )

    entries_by_id = {item["source_id"]: item for item in entries}
    priority_ids = set(selection["priority_source_ids"])
    supplemental_ids = set(selection["supplemental_source_ids"])
    if priority_ids & supplemental_ids:
        raise ValueError("scan source selection cannot duplicate source roles")
    selected_ids = priority_ids | supplemental_ids
    if selected_ids - set(entries_by_id):
        raise ValueError("scan source selection references unknown sources")
    for source_id in priority_ids:
        if entries_by_id[source_id]["discovery_role"] != "priority_direct":
            raise ValueError(
                f"scan priority source {source_id} does not have priority_direct role"
            )
    for source_id in supplemental_ids:
        if entries_by_id[source_id]["discovery_role"] != "supplemental_direct":
            raise ValueError(
                f"scan supplemental source {source_id} does not have supplemental_direct role"
            )
    if require_confirmed_sources:
        unconfirmed = sorted(
            source_id
            for source_id in selected_ids
            if entries_by_id[source_id]["review_status"] != "confirmed"
        )
        if unconfirmed:
            raise ValueError(
                "scan source selection requires confirmed source-plan entries: "
                + ", ".join(unconfirmed)
            )

    expected_scope = {
        (dimension, query_value)
        for dimension, field in QUERY_SCOPE_FIELDS.items()
        for query_value in query_context[field]
    }
    claims = selection["scope_coverage"]
    actual_scope = {(claim["dimension"], claim["query_value"]) for claim in claims}
    if len(actual_scope) != len(claims):
        raise ValueError("scan source selection contains duplicate scope claims")
    if actual_scope != expected_scope:
        raise ValueError(
            "scan source selection must cover every query territory and category exactly"
        )
    for claim in claims:
        claim_source_ids = set(claim["source_ids"])
        if claim_source_ids - selected_ids:
            raise ValueError("scan scope claim references an unselected source")
        if claim["status"] == "covered" and not claim_source_ids:
            raise ValueError("covered scan scope claim requires at least one source")
        if claim["status"] == "gap" and claim_source_ids:
            raise ValueError("gap scan scope claim cannot reference a source")


def _scan_coverage(
    *,
    priority_source_ids: list[str],
    unreviewed_priority_source_ids: list[str],
    source_checks: list[dict[str, Any]],
    selection_review_status: str,
    scope_gap_keys: list[str],
) -> dict[str, Any]:
    """Reproduce scan coverage from closed execution facts.

    This deterministic gate is justified by auditability: it checks whether
    every professionally selected priority source has a confirmed terminal
    check for the requested window. It does not select sources or judge their
    relevance, authority, or the meaning of any publication.
    """

    checks = {item["source_id"]: item for item in source_checks}
    priority_ids = set(priority_source_ids)
    verified = {
        source_id
        for source_id in priority_ids
        if source_id in checks
        and checks[source_id]["check_status"] == "checked"
        and checks[source_id]["check_review_status"] == "confirmed"
    }
    not_applicable = {
        source_id
        for source_id in priority_ids
        if source_id in checks
        and checks[source_id]["check_status"] == "not_applicable"
        and checks[source_id]["check_review_status"] == "confirmed"
    }
    unavailable = {
        source_id
        for source_id in priority_ids
        if source_id in checks
        and checks[source_id]["check_status"] == "unavailable"
        and checks[source_id]["check_review_status"] == "confirmed"
    }
    failed = {
        source_id
        for source_id in priority_ids
        if source_id in checks
        and checks[source_id]["check_status"] == "failed"
        and checks[source_id]["check_review_status"] == "confirmed"
    }
    resolved = verified | not_applicable
    unreviewed = set(unreviewed_priority_source_ids)
    unverified = sorted((priority_ids - resolved) | unreviewed)
    priority_count = len(priority_ids)
    completed_count = len(resolved)
    ratio = 0 if priority_count == 0 else completed_count * 10_000 // priority_count
    checked_times = [
        item["checked_at"] for item in source_checks if item["checked_at"] is not None
    ]
    if selection_review_status != "confirmed":
        status = "selection_unreviewed"
    elif unreviewed:
        status = "plan_unreviewed"
    elif scope_gap_keys:
        status = "scope_gaps"
    elif priority_count == 0:
        status = "no_priority_sources"
    elif completed_count == priority_count:
        status = "priority_sources_verified"
    elif not source_checks:
        status = "not_started"
    else:
        status = "partial"
    return {
        "priority_source_count": priority_count,
        "completed_priority_count": completed_count,
        "verified_priority_count": len(verified),
        "not_applicable_priority_count": len(not_applicable),
        "unavailable_priority_count": len(unavailable),
        "failed_priority_count": len(failed),
        "unreviewed_priority_count": len(unreviewed),
        "selection_review_status": selection_review_status,
        "scope_gap_count": len(scope_gap_keys),
        "uncovered_scope_keys": scope_gap_keys,
        "unverified_priority_source_ids": unverified,
        "ratio_basis_points": ratio,
        "last_checked_at": max(checked_times) if checked_times else None,
        "status": status,
        "statement": (
            f"{completed_count}/{priority_count} reviewed priority sources have a confirmed resolving result (checked or not_applicable); "
            f"{len(unavailable)} are unavailable and {len(failed)} failed; "
            f"{len(unreviewed)} selected priority sources still require plan review; "
            f"{len(scope_gap_keys)} query-scope dimensions have a declared gap; "
            "this is coverage of the professionally reviewed query-scoped source selection, not the probability that every opportunity was found."
        ),
    }


def _cursor(value: object, *, recorded_at: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("cursor_after must be an object or null")
    external_id = str(value.get("external_id") or "").strip() or None
    publication_date = value.get("publication_date")
    if publication_date is not None:
        publication_date = validate_iso_date(
            publication_date, field="cursor_after.publication_date"
        )
    official_url = str(value.get("official_url") or "").strip() or None
    if external_id is None and publication_date is None and official_url is None:
        raise ValueError(
            "cursor_after requires at least one observed publication field"
        )
    return {
        "external_id": external_id,
        "publication_date": publication_date,
        "official_url": official_url,
        "recorded_at": recorded_at,
    }


def _validate_economic_estimate(estimate: Mapping[str, Any], *, path: str) -> None:
    gross_min = _decimal(
        estimate.get("gross_benefit_min"), field=f"{path}.gross_benefit_min"
    )
    gross_max = _decimal(
        estimate.get("gross_benefit_max"), field=f"{path}.gross_benefit_max"
    )
    cost_min = _decimal(
        estimate.get("preparation_cost_min"), field=f"{path}.preparation_cost_min"
    )
    cost_max = _decimal(
        estimate.get("preparation_cost_max"), field=f"{path}.preparation_cost_max"
    )
    net_min = _decimal(estimate.get("net_value_min"), field=f"{path}.net_value_min")
    net_max = _decimal(estimate.get("net_value_max"), field=f"{path}.net_value_max")
    if min(gross_min, gross_max, cost_min, cost_max) < 0:
        raise ValueError(
            f"{path} benefit and preparation cost ranges cannot be negative"
        )
    if gross_min > gross_max or cost_min > cost_max:
        raise ValueError(f"{path} range minimum cannot exceed maximum")
    # Exact range arithmetic is deterministic because the professional/model
    # supplies every economic assumption; code only reproduces subtraction.
    if net_min != gross_min - cost_max or net_max != gross_max - cost_min:
        raise ValueError(f"{path} net value range does not reproduce exactly")


def _without_review_status(value: object) -> object:
    if isinstance(value, list):
        return [_without_review_status(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _without_review_status(item)
        for key, item in value.items()
        if key not in {"review_status", "check_review_status"}
    }


def _review_basis(scope: str, target: dict[str, Any]) -> object:
    """Return the exact mechanical state one professional decision binds."""

    if scope == "source":
        return _source_registry_basis(target)
    if scope == "source_check":
        fields = (
            "source_id",
            "check_id",
            "last_scan_id",
            "check_status",
            "checked_at",
            "window_start",
            "window_end",
            "next_check_on",
            "result_count",
            "error_code",
            "cursor_before",
            "cursor_after",
        )
        return {
            **{field: target[field] for field in fields},
            "issue_inventory": target.get("issue_inventory"),
        }
    return _without_review_status(target)


def _require_fresh_confirmation(
    radar: dict[str, Any], *, scope: str, target_id: str, target: dict[str, Any]
) -> None:
    expected_hash = canonical_json_sha256(_review_basis(scope, target))
    for event in reversed(radar["review_events"]):
        if event["scope"] == scope and event["target_id"] == target_id:
            if (
                event["decision"] != "accepted"
                or event["target_sha256"] != expected_hash
            ):
                raise ValueError(f"{scope} {target_id} has a stale professional review")
            return
    raise ValueError(f"{scope} {target_id} has no professional review")


def _validate_radar(radar: dict[str, Any]) -> None:
    secret_paths = prohibited_secret_paths(radar)
    if secret_paths:
        raise ValueError(
            "radar contains prohibited secret/session fields: "
            + ", ".join(secret_paths)
        )
    schema_issues = validate_artifact_schema("opportunity_radar", radar)
    if schema_issues:
        first = schema_issues[0]
        raise ValueError(f"{first['path']}: {first['message']}")

    evidence = radar["profile_evidence"]
    evidence_ids = _unique_ids(evidence, "evidence_id")
    evidence_owner = {item["evidence_id"]: item["client_ref"] for item in evidence}
    for item in evidence:
        if item["evidence_kind"] == "document_receipt" and item["sha256"] is None:
            raise ValueError(
                f"document evidence {item['evidence_id']} requires an exact SHA-256 receipt"
            )

    profiles = radar["profiles"]
    if radar["scope"] == "single_client" and len(profiles) > 1:
        raise ValueError("single_client radar cannot contain more than one profile")
    client_refs = _unique_ids(profiles, "client_ref")
    facet_owner: dict[str, str] = {}
    for profile in profiles:
        _unique_ids(profile["revision_history"], "revision_id")
        if profile["revision"] != len(profile["revision_history"]) + 1:
            raise ValueError(
                f"profile {profile['client_ref']} revision does not reproduce from history"
            )
        revision_times = [
            _datetime(item["observed_at"], field="profile revision observed_at")
            for item in profile["revision_history"]
        ]
        if revision_times != sorted(revision_times):
            raise ValueError(
                f"profile {profile['client_ref']} revisions are not chronological"
            )
        if profile["review_status"] == "confirmed" and any(
            item["review_status"] != "confirmed"
            for item in [*profile["facets"], *profile["revision_history"]]
        ):
            raise ValueError(
                f"confirmed profile {profile['client_ref']} has unconfirmed components"
            )
        for revision in profile["revision_history"]:
            if set(revision["evidence_refs"]) - evidence_ids:
                raise ValueError(
                    f"profile revision {revision['revision_id']} references unknown evidence"
                )
            if any(
                evidence_owner[evidence_id] != profile["client_ref"]
                for evidence_id in revision["evidence_refs"]
            ):
                raise ValueError(
                    f"profile revision {revision['revision_id']} references another client's evidence"
                )
        for facet in profile["facets"]:
            facet_id = safe_identifier(facet["facet_id"], field="facet_id")
            if facet_id in facet_owner:
                raise ValueError("duplicate facet_id")
            facet_owner[facet_id] = profile["client_ref"]
            refs = set(facet["evidence_refs"])
            if facet["provenance"] == "document_observation" and not refs:
                raise ValueError(
                    f"document-observed facet {facet_id} requires evidence"
                )
            if refs - evidence_ids:
                raise ValueError(f"facet {facet_id} references unknown evidence")
            if any(
                evidence_owner[evidence_id] != profile["client_ref"]
                for evidence_id in refs
            ):
                raise ValueError(
                    f"facet {facet_id} references another client's evidence"
                )

    entries = radar["source_plan"]["entries"]
    source_ids = _unique_ids(entries, "source_id")
    for entry in entries:
        unknown_profiles = set(entry["profile_refs"]) - client_refs
        if unknown_profiles:
            raise ValueError(f"source {entry['source_id']} references unknown profiles")
        _validate_issue_inventory(entry)
        status = entry["check_status"]
        if status == "planned" and entry["check_review_status"] == "confirmed":
            raise ValueError(
                f"planned source {entry['source_id']} cannot have a confirmed check review"
            )
        if status == "planned" and entry["checked_at"] is not None:
            raise ValueError(
                f"planned source {entry['source_id']} cannot have checked_at"
            )
        if status == "planned" and any(
            entry[field] is not None
            for field in (
                "check_id",
                "last_scan_id",
                "window_start",
                "window_end",
                "cursor_before",
                "cursor_after",
            )
        ):
            raise ValueError(
                f"planned source {entry['source_id']} cannot retain check evidence"
            )
        if status != "planned" and entry["checked_at"] is None:
            raise ValueError(f"source {entry['source_id']} requires checked_at")
        if status != "planned" and any(
            entry[field] is None
            for field in ("check_id", "last_scan_id", "window_start", "window_end")
        ):
            raise ValueError(
                f"source {entry['source_id']} requires scan-bound check evidence"
            )
        if entry["window_start"] and entry["window_end"]:
            if validate_iso_date(
                entry["window_start"], field="source check window_start"
            ) > validate_iso_date(entry["window_end"], field="source check window_end"):
                raise ValueError(
                    f"source {entry['source_id']} check window ends before it starts"
                )
        if status == "checked" and entry["result_count"] is None:
            raise ValueError(
                f"checked source {entry['source_id']} requires result_count"
            )
        if status == "failed" and not str(entry["error_code"] or "").strip():
            raise ValueError(f"failed source {entry['source_id']} requires error_code")
    expected_coverage = _coverage(entries)
    if radar["source_plan"]["coverage"] != expected_coverage:
        raise ValueError("source coverage does not reproduce from source checks")

    opportunities = radar["opportunities"]
    opportunity_ids = _unique_ids(opportunities, "opportunity_id")
    lifecycle_ids: set[str] = set()
    revision_ids: set[str] = set()
    for opportunity in opportunities:
        if opportunity["revision"] != len(opportunity["revision_history"]) + 1:
            raise ValueError(
                f"opportunity {opportunity['opportunity_id']} revision does not reproduce from history"
            )
        if set(opportunity["source_ids"]) - source_ids:
            raise ValueError(
                f"opportunity {opportunity['opportunity_id']} references unknown sources"
            )
        history = opportunity["lifecycle_history"]
        observed_times = [
            _datetime(item["observed_at"], field="lifecycle observed_at")
            for item in history
        ]
        if observed_times != sorted(observed_times):
            raise ValueError(
                f"opportunity {opportunity['opportunity_id']} lifecycle observations are not chronological"
            )
        if opportunity["current_lifecycle"] != history[-1]["status"]:
            raise ValueError(
                f"opportunity {opportunity['opportunity_id']} current lifecycle is stale"
            )
        for observation in history:
            observation_id = safe_identifier(
                observation["observation_id"], field="observation_id"
            )
            if observation_id in lifecycle_ids:
                raise ValueError("duplicate observation_id")
            lifecycle_ids.add(observation_id)
            if set(observation["source_ids"]) - source_ids:
                raise ValueError(
                    f"lifecycle observation {observation_id} references unknown sources"
                )
            if set(observation["source_ids"]) - set(opportunity["source_ids"]):
                raise ValueError(
                    f"lifecycle observation {observation_id} is outside its opportunity source set"
                )
        for revision in opportunity["revision_history"]:
            revision_id = safe_identifier(revision["revision_id"], field="revision_id")
            if revision_id in revision_ids:
                raise ValueError("duplicate revision_id")
            revision_ids.add(revision_id)
            if set(revision["source_ids"]) - source_ids:
                raise ValueError(
                    f"opportunity revision {revision_id} references unknown sources"
                )
            if set(revision["source_ids"]) - set(opportunity["source_ids"]):
                raise ValueError(
                    f"opportunity revision {revision_id} is outside its opportunity source set"
                )
        revision_times = [
            _datetime(item["observed_at"], field="opportunity revision observed_at")
            for item in opportunity["revision_history"]
        ]
        if revision_times != sorted(revision_times):
            raise ValueError(
                f"opportunity {opportunity['opportunity_id']} revisions are not chronological"
            )
        if opportunity["review_status"] == "confirmed" and any(
            item["review_status"] != "confirmed"
            for item in [
                *opportunity["lifecycle_history"],
                *opportunity["revision_history"],
            ]
        ):
            raise ValueError(
                f"confirmed opportunity {opportunity['opportunity_id']} has unconfirmed components"
            )
        opening = opportunity.get("opening_date")
        closing = opportunity.get("closing_date")
        if (
            opening
            and closing
            and validate_iso_date(opening, field="opening_date")
            > validate_iso_date(closing, field="closing_date")
        ):
            raise ValueError(
                f"opportunity {opportunity['opportunity_id']} closes before it opens"
            )

    matches = radar["matches"]
    _unique_ids(matches, "match_id")
    for index, match in enumerate(matches):
        if match["opportunity_id"] not in opportunity_ids:
            raise ValueError(
                f"match {match['match_id']} references unknown opportunity"
            )
        if match["client_ref"] not in client_refs:
            raise ValueError(f"match {match['match_id']} references unknown client")
        if set(match["source_ids"]) - source_ids:
            raise ValueError(f"match {match['match_id']} references unknown sources")
        for facet_id in match["profile_facet_ids"]:
            if facet_owner.get(facet_id) != match["client_ref"]:
                raise ValueError(
                    f"match {match['match_id']} references another client's facet"
                )
        estimate = match.get("economic_estimate")
        if estimate is not None:
            _validate_economic_estimate(
                estimate, path=f"matches[{index}].economic_estimate"
            )
            if (
                match["review_status"] == "confirmed"
                and estimate["review_status"] != "confirmed"
            ):
                raise ValueError(
                    f"confirmed match {match['match_id']} has an unconfirmed economic estimate"
                )

    scan_ids: set[str] = set()
    for scan in radar["monitoring"]["scan_history"]:
        scan_id = safe_identifier(scan["scan_id"], field="scan_id")
        if scan_id in scan_ids:
            raise ValueError("duplicate scan_id")
        scan_ids.add(scan_id)
        selection = scan["source_selection"]
        _validate_scan_source_selection(
            selection=selection,
            query_context=scan["query_context"],
            entries=entries,
            require_confirmed_sources=False,
        )
        selected_source_ids = _selection_source_ids(selection)
        if set(scan["priority_source_ids"]) != set(selection["priority_source_ids"]):
            raise ValueError(f"scan {scan_id} priority selection does not reproduce")
        if set(scan["source_ids"]) - source_ids:
            raise ValueError(f"scan {scan_id} references unknown sources")
        if set(scan["source_ids"]) - selected_source_ids:
            raise ValueError(f"scan {scan_id} contains an unselected source check")
        if (
            set(scan["priority_source_ids"]) - source_ids
            or set(scan["unreviewed_priority_source_ids"]) - source_ids
        ):
            raise ValueError(
                f"scan {scan_id} priority registry is not reference-closed"
            )
        if set(scan["unreviewed_priority_source_ids"]) - set(
            scan["priority_source_ids"]
        ):
            raise ValueError(f"scan {scan_id} has an invalid pending priority source")
        snapshots = scan["source_check_snapshots"]
        if set(scan["source_ids"]) != _unique_ids(snapshots, "source_id"):
            raise ValueError(f"scan {scan_id} source snapshots do not reproduce")
        _unique_ids(snapshots, "check_id")
        if any(item["last_scan_id"] != scan_id for item in snapshots):
            raise ValueError(f"scan {scan_id} contains a check from another scan")
        if validate_iso_date(
            scan["window_start"], field="scan window_start"
        ) > validate_iso_date(scan["window_end"], field="scan window_end"):
            raise ValueError(f"scan {scan_id} window ends before it starts")
        for snapshot in snapshots:
            _validate_issue_inventory(snapshot)
            if (
                snapshot["window_start"] > scan["window_start"]
                or snapshot["window_end"] < scan["window_end"]
            ):
                raise ValueError(
                    f"scan {scan_id} source {snapshot['source_id']} does not cover the requested window"
                )
        expected_scan_coverage = _scan_coverage(
            priority_source_ids=scan["priority_source_ids"],
            unreviewed_priority_source_ids=scan["unreviewed_priority_source_ids"],
            source_checks=snapshots,
            selection_review_status=selection["review_status"],
            scope_gap_keys=_scope_gap_keys(selection),
        )
        if scan["coverage"] != expected_scan_coverage:
            raise ValueError(f"scan {scan_id} coverage does not reproduce")
        if scan["outcome"] == "running" and scan["completed_at"] is not None:
            raise ValueError(f"running scan {scan_id} cannot have completed_at")
        if scan["outcome"] != "running" and scan["completed_at"] is None:
            raise ValueError(f"completed scan {scan_id} requires completed_at")
        if scan["completed_at"] is not None and _datetime(
            scan["completed_at"], field="scan completed_at"
        ) < _datetime(scan["started_at"], field="scan started_at"):
            raise ValueError(f"scan {scan_id} completes before it starts")
        if scan["completed_at"] is not None and any(
            _datetime(item["checked_at"], field="source checked_at")
            > _datetime(scan["completed_at"], field="scan completed_at")
            for item in snapshots
        ):
            raise ValueError(f"scan {scan_id} completes before a source check")
        if scan["outcome"] == "running" and snapshots:
            raise ValueError(f"running scan {scan_id} cannot seal source snapshots")
        if (
            scan["outcome"] == "complete"
            and scan["coverage"]["status"] != "priority_sources_verified"
        ):
            raise ValueError(
                f"scan {scan_id} cannot claim complete while source selection, query scope, or priority sources are unresolved"
            )
        semantic_web = scan["semantic_web_check"]
        if semantic_web["status"] == "not_run" and any(
            semantic_web[field] is not None
            for field in ("checked_at", "result_count", "error_code")
        ):
            raise ValueError(f"scan {scan_id} semantic web check has an invalid time")
        if semantic_web["status"] != "not_run" and semantic_web["checked_at"] is None:
            raise ValueError(f"scan {scan_id} semantic web check requires checked_at")
        if (
            semantic_web["checked_at"] is not None
            and scan["completed_at"] is not None
            and _datetime(semantic_web["checked_at"], field="semantic web checked_at")
            > _datetime(scan["completed_at"], field="scan completed_at")
        ):
            raise ValueError(f"scan {scan_id} completes before semantic web search")
        if semantic_web["status"] == "checked" and semantic_web["result_count"] is None:
            raise ValueError(f"scan {scan_id} semantic web check requires result_count")
        if (
            semantic_web["status"] == "failed"
            and not str(semantic_web["error_code"] or "").strip()
        ):
            raise ValueError(
                f"scan {scan_id} failed semantic web check requires error_code"
            )
        priority_attempts = [
            item
            for item in snapshots
            if item["source_id"] in scan["priority_source_ids"]
        ]
        if semantic_web["status"] != "not_run":
            if len(priority_attempts) != len(scan["priority_source_ids"]):
                raise ValueError(
                    f"scan {scan_id} semantic web search cannot precede priority-source attempts"
                )
            latest_direct = max(
                (
                    _datetime(item["checked_at"], field="source checked_at")
                    for item in priority_attempts
                ),
                default=None,
            )
            if (
                latest_direct is not None
                and _datetime(
                    semantic_web["checked_at"], field="semantic web checked_at"
                )
                < latest_direct
            ):
                raise ValueError(
                    f"scan {scan_id} semantic web search precedes a priority-source check"
                )

    scans_by_id = {
        item["scan_id"]: item for item in radar["monitoring"]["scan_history"]
    }
    for entry in entries:
        if entry["last_scan_id"] is None:
            continue
        scan = scans_by_id.get(entry["last_scan_id"])
        if scan is None:
            raise ValueError(
                f"source {entry['source_id']} references unknown last_scan_id"
            )
        if _datetime(entry["checked_at"], field="source checked_at") < _datetime(
            scan["started_at"], field="scan started_at"
        ):
            raise ValueError(
                f"source {entry['source_id']} was checked before its scan started"
            )

    scan_times = [
        _datetime(scan.get("completed_at") or scan["started_at"], field="scan time")
        for scan in radar["monitoring"]["scan_history"]
    ]
    recorded_last_scan = radar["monitoring"]["last_scan_at"]
    if scan_times:
        if recorded_last_scan is None or _datetime(
            recorded_last_scan, field="monitoring last_scan_at"
        ) != max(scan_times):
            raise ValueError(
                "monitoring last_scan_at does not reproduce from scan history"
            )
    elif recorded_last_scan is not None:
        raise ValueError("monitoring last_scan_at requires scan history")

    for item in evidence:
        if item["review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="evidence",
                target_id=item["evidence_id"],
                target=item,
            )
    for profile in profiles:
        if profile["review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="profile",
                target_id=profile["client_ref"],
                target=profile,
            )
    for entry in entries:
        if entry["review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="source",
                target_id=entry["source_id"],
                target=entry,
            )
        if entry["check_review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="source_check",
                target_id=entry["source_id"],
                target=entry,
            )
    for scan in radar["monitoring"]["scan_history"]:
        selection = scan["source_selection"]
        if selection["review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="scan_source_selection",
                target_id=scan["scan_id"],
                target=selection,
            )
    for opportunity in opportunities:
        if opportunity["review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="opportunity",
                target_id=opportunity["opportunity_id"],
                target=opportunity,
            )
    for match in matches:
        if match["review_status"] == "confirmed":
            _require_fresh_confirmation(
                radar,
                scope="match",
                target_id=match["match_id"],
                target=match,
            )

    review_event_ids = [item["event_id"] for item in radar["review_events"]]
    if len(review_event_ids) != len(set(review_event_ids)):
        raise ValueError("duplicate review event_id")
    review_keys = [item["idempotency_key"] for item in radar["review_events"]]
    if len(review_keys) != len(set(review_keys)):
        raise ValueError("duplicate review event idempotency_key")

    operation_keys = [item["idempotency_key"] for item in radar["operations"]]
    if len(operation_keys) != len(set(operation_keys)):
        raise ValueError("duplicate operation idempotency_key")
    if set(review_keys) - set(operation_keys):
        raise ValueError("review event has no matching idempotent operation")


def load_validated_radar(workspace: Path) -> dict[str, Any]:
    """Load and exhaustively validate one radar artifact."""

    radar = load_json_object(_radar_path(workspace))
    _validate_radar(radar)
    if radar["workspace_binding"]["workspace_path_sha256"] != _workspace_sha256(
        workspace
    ):
        raise PermissionError("radar belongs to another private studio workspace")
    return radar


def initialize_radar(
    workspace: Path,
    *,
    radar_id: str,
    workspace_id: str,
    reference_date: str,
    scope: str,
    authorized_by: str,
    retention_owner: str,
    confirmed_by_user: bool,
) -> Path:
    """Create an empty private radar without selecting sources or legal meaning."""

    radar_id = safe_identifier(radar_id, field="radar_id")
    workspace_id = safe_identifier(workspace_id, field="workspace_id")
    authorized_by = safe_identifier(authorized_by, field="authorized_by")
    retention_owner = str(retention_owner).strip()
    if confirmed_by_user is not True:
        raise ValueError("explicit user confirmation is required")
    if not retention_owner:
        raise ValueError("retention_owner is required")
    reference_date = validate_iso_date(reference_date, field="reference_date")
    if scope not in {"single_client", "portfolio"}:
        raise ValueError("scope must be single_client or portfolio")
    path = _radar_path(workspace)
    with case_lock(path.parent):
        if path.exists():
            radar = load_json_object(path)
            if (
                radar.get("radar_id") != radar_id
                or radar.get("workspace_binding", {}).get("workspace_id")
                != workspace_id
                or radar.get("reference_date") != reference_date
                or radar.get("scope") != scope
                or radar.get("workspace_binding", {}).get("authorized_by")
                != authorized_by
                or radar.get("workspace_binding", {}).get("retention_owner")
                != retention_owner
            ):
                raise ValueError(
                    "existing radar initialization parameters do not match"
                )
            _validate_radar(radar)
            if radar["workspace_binding"]["workspace_path_sha256"] != _workspace_sha256(
                workspace
            ):
                raise PermissionError(
                    "radar belongs to another private studio workspace"
                )
            return path
        created_at = iso_now()
        radar = {
            "schema_version": "3.0",
            "plugin": PLUGIN_NAME,
            "radar_id": radar_id,
            "scope": scope,
            "reference_date": reference_date,
            "revision": 0,
            "created_at": created_at,
            "updated_at": created_at,
            "workspace_binding": {
                "workspace_id": workspace_id,
                "workspace_path_sha256": _workspace_sha256(workspace),
                "authorized_by": authorized_by,
                "authorization_basis": "explicit_user_confirmation",
                "identity_assurance": "asserted_not_authenticated",
                "authorized_at": created_at,
                "retention_owner": retention_owner,
                "portable_client_run_created": False,
            },
            "profile_evidence": [],
            "profiles": [],
            "source_plan": {"entries": [], "coverage": _coverage([])},
            "opportunities": [],
            "matches": [],
            "monitoring": {
                "last_scan_at": None,
                "next_scan_on": None,
                "scan_history": [],
            },
            "review_events": [],
            "operations": [],
            "limitations": [
                "Coverage measures direct checks of the reviewed priority-source registry, not all grants in existence.",
                "Compatibility, lifecycle meaning, economic assumptions and recommended action require professional review.",
                "Semantic web search is supplemental; source selection and act meaning remain model-led and professionally reviewed.",
                "The radar never authenticates to portals, contacts clients, signs, saves or submits applications.",
            ],
        }
        _validate_radar(radar)
        write_private_json(path, radar)
    return path


def _operation_result(
    radar: dict[str, Any], *, idempotency_key: str, operation: str, payload: object
) -> bool:
    key = safe_identifier(idempotency_key, field="idempotency_key")

    def stable_payload(value: object) -> object:
        """Exclude generated contribution timestamps from retry identity."""

        if isinstance(value, list):
            return [stable_payload(item) for item in value]
        if not isinstance(value, dict):
            return value
        normalized = {key: stable_payload(item) for key, item in value.items()}
        contribution = normalized.get("contribution")
        if isinstance(contribution, dict):
            contribution.pop("recorded_at", None)
        return normalized

    payload_sha256 = canonical_json_sha256(operation, stable_payload(payload))
    for existing in radar["operations"]:
        if existing["idempotency_key"] != key:
            continue
        if (
            existing["operation"] == operation
            and existing["payload_sha256"] == payload_sha256
        ):
            return False
        raise ValueError(
            "idempotency key already used for another operation or payload"
        )
    radar["operations"].append(
        {
            "idempotency_key": key,
            "operation": operation,
            "payload_sha256": payload_sha256,
            "recorded_at": iso_now(),
        }
    )
    return True


def _mutate(
    workspace: Path,
    *,
    operation: str,
    payload: object,
    idempotency_key: str,
    mutation: Callable[[dict[str, Any]], dict[str, Any]],
    retry_result: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    path = _radar_path(workspace)
    with case_lock(path.parent):
        current = load_json_object(path)
        _validate_radar(current)
        if current["workspace_binding"]["workspace_path_sha256"] != _workspace_sha256(
            workspace
        ):
            raise PermissionError("radar belongs to another private studio workspace")
        candidate = deepcopy(current)
        if not _operation_result(
            candidate,
            idempotency_key=idempotency_key,
            operation=operation,
            payload=payload,
        ):
            return retry_result(current)
        result = mutation(candidate)
        candidate["source_plan"]["coverage"] = _coverage(
            candidate["source_plan"]["entries"]
        )
        candidate["revision"] += 1
        candidate["updated_at"] = iso_now()
        _validate_radar(candidate)
        write_private_json(path, candidate)
        return result


def record_profile_evidence(
    workspace: Path,
    *,
    evidence: dict[str, Any],
    idempotency_key: str,
    origin: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    model_session_ref: str | None = None,
) -> dict[str, Any]:
    """Record one opaque, receipted profile-evidence reference."""

    payload = deepcopy(evidence)
    payload["evidence_id"] = safe_identifier(
        payload.get("evidence_id"), field="evidence_id"
    )
    payload["client_ref"] = safe_identifier(
        payload.get("client_ref"), field="client_ref"
    )
    payload["receipt_ref"] = safe_identifier(
        payload.get("receipt_ref"), field="receipt_ref"
    )
    payload["review_status"] = "proposed"
    payload["contribution"] = _contribution(
        origin=origin,
        provider=provider,
        model=model,
        prompt_template_version=prompt_template_version,
        recorded_by=recorded_by,
        model_session_ref=model_session_ref,
    )
    _reject_unmistakable_secret_values(payload, label="profile_evidence")

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        _assert_client_mapping_session_isolated(
            radar,
            client_ref=payload["client_ref"],
            model_session_ref=payload["contribution"]["model_session_ref"],
        )
        for item in radar["profile_evidence"]:
            if item["evidence_id"] == payload["evidence_id"]:
                raise ValueError("evidence_id already exists; preserve its receipt")
        radar["profile_evidence"].append(payload)
        return payload

    return _mutate(
        workspace,
        operation="record_profile_evidence",
        payload=payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["profile_evidence"], "evidence_id", payload["evidence_id"]
        ),
    )


def _revision_event(
    value: object,
    *,
    previous: dict[str, Any],
    changed_fields: list[str],
    evidence_refs: list[str],
    source_ids: list[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("a revision_event is required to change confirmed work")
    return {
        "revision_id": safe_identifier(value.get("revision_id"), field="revision_id"),
        "observed_at": str(value.get("observed_at", "")),
        "rationale": str(value.get("rationale", "")).strip(),
        "evidence_refs": evidence_refs,
        "source_ids": source_ids,
        "changed_fields": changed_fields,
        "previous_sha256": canonical_json_sha256(_without_review_status(previous)),
        "review_status": "proposed",
    }


def record_profile(
    workspace: Path,
    *,
    profile: dict[str, Any],
    idempotency_key: str,
    origin: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    model_session_ref: str | None = None,
) -> dict[str, Any]:
    """Record one opaque company opportunity profile as a reviewable proposal."""

    payload = deepcopy(profile)
    requested_revision = payload.pop("revision_event", None)
    payload["client_ref"] = safe_identifier(
        payload.get("client_ref"), field="client_ref"
    )
    payload["review_status"] = "proposed"
    payload["revision"] = 1
    payload["revision_history"] = []
    for facet in payload.get("facets", []):
        facet["review_status"] = "proposed"
    payload["contribution"] = _contribution(
        origin=origin,
        provider=provider,
        model=model,
        prompt_template_version=prompt_template_version,
        recorded_by=recorded_by,
        model_session_ref=model_session_ref,
    )
    _reject_unmistakable_secret_values(payload, label="profile")

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        _assert_client_mapping_session_isolated(
            radar,
            client_ref=payload["client_ref"],
            model_session_ref=payload["contribution"]["model_session_ref"],
        )
        profiles = radar["profiles"]
        for index, existing in enumerate(profiles):
            if existing["client_ref"] == payload["client_ref"]:
                if existing["review_status"] == "confirmed":
                    old_facets = _without_review_status(existing["facets"])
                    new_facets = _without_review_status(payload["facets"])
                    if old_facets == new_facets:
                        return existing
                    evidence_refs = sorted(
                        {
                            evidence_id
                            for facet in payload["facets"]
                            for evidence_id in facet["evidence_refs"]
                        }
                    )
                    event = _revision_event(
                        requested_revision,
                        previous=existing,
                        changed_fields=["facets"],
                        evidence_refs=evidence_refs,
                        source_ids=[],
                    )
                    payload["revision"] = existing["revision"] + 1
                    payload["revision_history"] = [
                        *existing["revision_history"],
                        event,
                    ]
                    for match in radar["matches"]:
                        if match["client_ref"] == payload["client_ref"]:
                            match["review_status"] = "proposed"
                            if match.get("economic_estimate") is not None:
                                match["economic_estimate"]["review_status"] = "proposed"
                else:
                    payload["revision"] = existing["revision"]
                    payload["revision_history"] = existing["revision_history"]
                profiles[index] = payload
                return payload
        profiles.append(payload)
        return payload

    return _mutate(
        workspace,
        operation="record_profile",
        payload=payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["profiles"], "client_ref", payload["client_ref"]
        ),
    )


def record_source(
    workspace: Path,
    *,
    source: dict[str, Any],
    idempotency_key: str,
    origin: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    model_session_ref: str | None = None,
) -> dict[str, Any]:
    """Record a model- or professional-selected official source plan entry."""

    payload = deepcopy(source)
    payload["source_id"] = safe_identifier(payload.get("source_id"), field="source_id")
    payload.update(
        {
            "check_status": "planned",
            "check_id": None,
            "last_scan_id": None,
            "checked_at": None,
            "window_start": None,
            "window_end": None,
            "result_count": None,
            "error_code": None,
            "cursor_before": None,
            "cursor_after": None,
            "review_status": "proposed",
            "check_review_status": "proposed",
            "contribution": _contribution(
                origin=origin,
                provider=provider,
                model=model,
                prompt_template_version=prompt_template_version,
                recorded_by=recorded_by,
                model_session_ref=model_session_ref,
            ),
        }
    )
    _reject_unmistakable_secret_values(payload, label="source")

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        _assert_non_mapping_session_isolated(
            radar,
            model_session_ref=payload["contribution"]["model_session_ref"],
        )
        entries = radar["source_plan"]["entries"]
        for existing in entries:
            if existing["source_id"] == payload["source_id"]:
                raise ValueError("source_id already exists; preserve its check history")
        entries.append(payload)
        return payload

    return _mutate(
        workspace,
        operation="record_source",
        payload=payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["source_plan"]["entries"], "source_id", payload["source_id"]
        ),
    )


def record_source_check(
    workspace: Path,
    *,
    source_id: str,
    check_id: str,
    scan_id: str,
    check_status: str,
    checked_at: str | None,
    window_start: str,
    window_end: str,
    next_check_on: str | None,
    result_count: int | None,
    error_code: str | None,
    cursor_after: dict[str, Any] | None,
    idempotency_key: str,
    issue_inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one direct-source check bound to a running temporal scan."""

    source_id = safe_identifier(source_id, field="source_id")
    check_id = safe_identifier(check_id, field="check_id")
    scan_id = safe_identifier(scan_id, field="scan_id")
    if check_status not in CHECK_STATUSES - {"planned"}:
        raise ValueError("unsupported check_status")
    if checked_at is None:
        raise ValueError("checked_at is required")
    _datetime(checked_at, field="checked_at")
    window_start = validate_iso_date(window_start, field="window_start")
    window_end = validate_iso_date(window_end, field="window_end")
    if window_start > window_end:
        raise ValueError("source check window ends before it starts")
    if next_check_on is not None:
        next_check_on = validate_iso_date(next_check_on, field="next_check_on")
    normalized_cursor = _cursor(cursor_after, recorded_at=checked_at)
    operation_payload = {
        "source_id": source_id,
        "check_id": check_id,
        "last_scan_id": scan_id,
        "check_status": check_status,
        "checked_at": checked_at,
        "window_start": window_start,
        "window_end": window_end,
        "next_check_on": next_check_on,
        "result_count": result_count,
        "error_code": error_code,
        "cursor_after": normalized_cursor,
        "issue_inventory": deepcopy(issue_inventory),
    }

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        entry = _find(radar["source_plan"]["entries"], "source_id", source_id)
        scan = _find(radar["monitoring"]["scan_history"], "scan_id", scan_id)
        if scan["outcome"] != "running":
            raise ValueError("source checks require a running scan")
        if scan["source_selection"]["review_status"] != "confirmed":
            raise ValueError(
                "source checks require a confirmed query-scoped source selection"
            )
        if source_id not in _selection_source_ids(scan["source_selection"]):
            raise ValueError("source check is outside the scan source selection")
        if entry["review_status"] != "confirmed":
            raise ValueError("source check requires a confirmed source-plan entry")
        if entry["last_scan_id"] not in {None, scan_id}:
            prior_scan = _find(
                radar["monitoring"]["scan_history"],
                "scan_id",
                entry["last_scan_id"],
            )
            if prior_scan["outcome"] == "running":
                raise ValueError(
                    "complete or fail the prior source scan before recording a newer check"
                )
        if _datetime(checked_at, field="checked_at") < _datetime(
            scan["started_at"], field="scan started_at"
        ):
            raise ValueError("source check cannot precede its scan")
        if window_start > scan["window_start"] or window_end < scan["window_end"]:
            raise ValueError("source check does not cover the scan window")
        operation_payload["cursor_before"] = deepcopy(entry["cursor_after"])
        if operation_payload["cursor_after"] is None:
            operation_payload["cursor_after"] = deepcopy(entry["cursor_after"])
        entry.update(operation_payload)
        entry["check_review_status"] = "proposed"
        return entry

    return _mutate(
        workspace,
        operation="record_source_check",
        payload=operation_payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["source_plan"]["entries"], "source_id", source_id
        ),
    )


def record_opportunity(
    workspace: Path,
    *,
    opportunity: dict[str, Any],
    idempotency_key: str,
    origin: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    model_session_ref: str | None = None,
) -> dict[str, Any]:
    """Record one source-backed opportunity and its time-aware status history."""

    payload = deepcopy(opportunity)
    requested_revision = payload.pop("revision_event", None)
    payload["opportunity_id"] = safe_identifier(
        payload.get("opportunity_id"), field="opportunity_id"
    )
    history = payload.get("lifecycle_history", [])
    for observation in history:
        observation["review_status"] = "proposed"
    if history:
        payload["current_lifecycle"] = history[-1]["status"]
    payload["review_status"] = "proposed"
    payload["revision"] = 1
    payload["revision_history"] = []
    payload["contribution"] = _contribution(
        origin=origin,
        provider=provider,
        model=model,
        prompt_template_version=prompt_template_version,
        recorded_by=recorded_by,
        model_session_ref=model_session_ref,
    )
    _reject_unmistakable_secret_values(payload, label="opportunity")

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        _assert_non_mapping_session_isolated(
            radar,
            model_session_ref=payload["contribution"]["model_session_ref"],
        )
        opportunities = radar["opportunities"]
        for index, existing in enumerate(opportunities):
            if existing["opportunity_id"] == payload["opportunity_id"]:
                if existing["review_status"] == "confirmed":
                    old_history = existing["lifecycle_history"]
                    incoming_history = payload["lifecycle_history"]
                    comparable_old = [
                        {
                            key: value
                            for key, value in item.items()
                            if key != "review_status"
                        }
                        for item in old_history
                    ]
                    comparable_incoming = [
                        {
                            key: value
                            for key, value in item.items()
                            if key != "review_status"
                        }
                        for item in incoming_history[: len(old_history)]
                    ]
                    revisable_fields = {
                        "opportunity_id",
                        "official_title",
                        "issuer",
                        "official_url",
                        "opening_date",
                        "closing_date",
                        "summary",
                    }
                    changed_fields = sorted(
                        key
                        for key in revisable_fields - {"opportunity_id"}
                        if existing[key] != payload[key]
                    )
                    if (
                        len(incoming_history) < len(old_history)
                        or comparable_incoming != comparable_old
                    ):
                        raise ValueError(
                            "confirmed opportunity history cannot be rewritten"
                        )
                    if not set(existing["source_ids"]).issubset(payload["source_ids"]):
                        raise ValueError(
                            "confirmed opportunity sources cannot be removed"
                        )
                    if len(incoming_history) > len(old_history):
                        changed_fields.append("lifecycle_history")
                    if set(payload["source_ids"]) != set(existing["source_ids"]):
                        changed_fields.append("source_ids")
                    if not changed_fields:
                        return existing
                    event = _revision_event(
                        requested_revision,
                        previous=existing,
                        changed_fields=sorted(set(changed_fields)),
                        evidence_refs=[],
                        source_ids=sorted(set(payload["source_ids"])),
                    )
                    payload["revision"] = existing["revision"] + 1
                    payload["revision_history"] = [
                        *existing["revision_history"],
                        event,
                    ]
                    payload["lifecycle_history"] = [
                        *old_history,
                        *incoming_history[len(old_history) :],
                    ]
                    payload["current_lifecycle"] = payload["lifecycle_history"][-1][
                        "status"
                    ]
                    for match in radar["matches"]:
                        if match["opportunity_id"] == payload["opportunity_id"]:
                            match["review_status"] = "proposed"
                            if match.get("economic_estimate") is not None:
                                match["economic_estimate"]["review_status"] = "proposed"
                else:
                    payload["revision"] = existing["revision"]
                    payload["revision_history"] = existing["revision_history"]
                opportunities[index] = payload
                return payload
        opportunities.append(payload)
        return payload

    return _mutate(
        workspace,
        operation="record_opportunity",
        payload=payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["opportunities"], "opportunity_id", payload["opportunity_id"]
        ),
    )


def record_match(
    workspace: Path,
    *,
    match: dict[str, Any],
    idempotency_key: str,
    origin: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    model_session_ref: str | None = None,
) -> dict[str, Any]:
    """Record a bidirectional client/opportunity match as a semantic proposal."""

    payload = deepcopy(match)
    payload["match_id"] = safe_identifier(payload.get("match_id"), field="match_id")
    payload["review_status"] = "proposed"
    if payload.get("economic_estimate") is not None:
        payload["economic_estimate"]["review_status"] = "proposed"
    payload["contribution"] = _contribution(
        origin=origin,
        provider=provider,
        model=model,
        prompt_template_version=prompt_template_version,
        recorded_by=recorded_by,
        model_session_ref=model_session_ref,
    )
    _reject_unmistakable_secret_values(payload, label="match")

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        _assert_non_mapping_session_isolated(
            radar,
            model_session_ref=payload["contribution"]["model_session_ref"],
        )
        matches = radar["matches"]
        for index, existing in enumerate(matches):
            if existing["match_id"] == payload["match_id"]:
                if existing["review_status"] == "confirmed":
                    raise ValueError("confirmed match cannot be overwritten")
                matches[index] = payload
                return payload
        matches.append(payload)
        return payload

    return _mutate(
        workspace,
        operation="record_match",
        payload=payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["matches"], "match_id", payload["match_id"]
        ),
    )


def record_scan(
    workspace: Path,
    *,
    scan: dict[str, Any],
    next_scan_on: str | None,
    idempotency_key: str,
    origin: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_template_version: str | None = None,
    recorded_by: str | None = None,
    model_session_ref: str | None = None,
) -> dict[str, Any]:
    """Start or seal one resumable, source-first temporal discovery scan."""

    payload = deepcopy(scan)
    payload["scan_id"] = safe_identifier(payload.get("scan_id"), field="scan_id")
    payload["window_start"] = validate_iso_date(
        payload.get("window_start"), field="scan.window_start"
    )
    payload["window_end"] = validate_iso_date(
        payload.get("window_end"), field="scan.window_end"
    )
    if payload["window_start"] > payload["window_end"]:
        raise ValueError("scan window ends before it starts")
    semantic_web = payload.get(
        "semantic_web_check",
        {
            "status": "not_run",
            "checked_at": None,
            "result_count": None,
            "error_code": None,
        },
    )
    if (
        not isinstance(semantic_web, dict)
        or semantic_web.get("status") not in SEMANTIC_WEB_STATUSES
    ):
        raise ValueError("unsupported semantic_web_check")
    payload["semantic_web_check"] = semantic_web
    if next_scan_on is not None:
        next_scan_on = validate_iso_date(next_scan_on, field="next_scan_on")

    selection_provenance = {
        "origin": origin,
        "provider": provider,
        "model": model,
        "prompt_template_version": prompt_template_version,
        "recorded_by": recorded_by,
    }

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        history = radar["monitoring"]["scan_history"]
        existing_index = next(
            (
                index
                for index, item in enumerate(history)
                if item["scan_id"] == payload["scan_id"]
            ),
            None,
        )
        entries = radar["source_plan"]["entries"]

        def prepare_selection() -> dict[str, Any]:
            selection = deepcopy(payload.get("source_selection"))
            if not isinstance(selection, dict):
                raise ValueError("a running scan requires a source_selection proposal")
            if any(value is None for value in selection_provenance.values()):
                raise ValueError(
                    "a source-selection proposal requires exact contribution provenance"
                )
            selection["review_status"] = "proposed"
            selection["contribution"] = _contribution(
                origin=str(origin),
                provider=str(provider),
                model=str(model),
                prompt_template_version=str(prompt_template_version),
                recorded_by=str(recorded_by),
                model_session_ref=model_session_ref,
            )
            _assert_non_mapping_session_isolated(
                radar,
                model_session_ref=selection["contribution"]["model_session_ref"],
            )
            _validate_scan_source_selection(
                selection=selection,
                query_context=payload["query_context"],
                entries=entries,
                require_confirmed_sources=True,
            )
            return selection

        def selected_entries(selection: Mapping[str, Any]) -> list[dict[str, Any]]:
            selected_ids = _selection_source_ids(selection)
            return [item for item in entries if item["source_id"] in selected_ids]

        def initialize_running_scan(selection: dict[str, Any]) -> None:
            priority_ids = sorted(selection["priority_source_ids"])
            selected = selected_entries(selection)
            payload.update(
                {
                    "source_selection": selection,
                    "source_plan_sha256": _source_registry_sha256(selected),
                    "priority_source_ids": priority_ids,
                    "unreviewed_priority_source_ids": [],
                    "source_ids": [],
                    "source_check_snapshots": [],
                    "coverage": _scan_coverage(
                        priority_source_ids=priority_ids,
                        unreviewed_priority_source_ids=[],
                        source_checks=[],
                        selection_review_status=selection["review_status"],
                        scope_gap_keys=_scope_gap_keys(selection),
                    ),
                }
            )

        if existing_index is None:
            if payload["outcome"] != "running":
                raise ValueError("a scan must be recorded as running before completion")
            initialize_running_scan(prepare_selection())
            history.append(payload)
        else:
            existing = history[existing_index]
            if existing["outcome"] != "running":
                raise ValueError("completed scan cannot be overwritten")
            for field in (
                "started_at",
                "window_start",
                "window_end",
                "query_context",
            ):
                if payload[field] != existing[field]:
                    raise ValueError(f"running scan cannot change {field}")
            if payload["outcome"] == "running":
                if existing["source_selection"]["review_status"] == "confirmed":
                    raise ValueError(
                        "a confirmed scan source selection cannot be overwritten"
                    )
                if any(item["last_scan_id"] == payload["scan_id"] for item in entries):
                    raise ValueError(
                        "a scan source selection cannot change after source checks"
                    )
                initialize_running_scan(prepare_selection())
                history[existing_index] = payload
                radar["monitoring"]["next_scan_on"] = next_scan_on
                return payload

            selection = existing["source_selection"]
            requested_selection = payload.get("source_selection")
            if requested_selection is not None and (
                not isinstance(requested_selection, dict)
                or _source_selection_proposal_basis(requested_selection)
                != _source_selection_proposal_basis(selection)
            ):
                raise ValueError("terminal scan cannot change source_selection")
            selected = selected_entries(selection)
            if _source_registry_sha256(selected) != existing["source_plan_sha256"]:
                raise ValueError(
                    "selected source registry changed during scan; start a new scan for reviewable coverage"
                )
            unreviewed_priority_ids = sorted(
                item["source_id"]
                for item in selected
                if item["source_id"] in existing["priority_source_ids"]
                and item["review_status"] != "confirmed"
            )
            snapshots = sorted(
                (
                    _source_check_snapshot(item)
                    for item in entries
                    if item["last_scan_id"] == payload["scan_id"]
                ),
                key=lambda item: item["source_id"],
            )
            coverage = _scan_coverage(
                priority_source_ids=existing["priority_source_ids"],
                unreviewed_priority_source_ids=unreviewed_priority_ids,
                source_checks=snapshots,
                selection_review_status=selection["review_status"],
                scope_gap_keys=_scope_gap_keys(selection),
            )
            payload.update(
                {
                    "source_selection": deepcopy(selection),
                    "source_plan_sha256": existing["source_plan_sha256"],
                    "priority_source_ids": existing["priority_source_ids"],
                    "unreviewed_priority_source_ids": unreviewed_priority_ids,
                    "source_ids": [item["source_id"] for item in snapshots],
                    "source_check_snapshots": snapshots,
                    "coverage": coverage,
                }
            )
            if (
                payload["outcome"] == "complete"
                and coverage["status"] != "priority_sources_verified"
            ):
                raise ValueError(
                    "scan cannot be complete while source selection, query scope, or priority sources are unresolved"
                )
            history[existing_index] = payload
        latest = max(
            history,
            key=lambda item: _datetime(
                item.get("completed_at") or item["started_at"], field="scan time"
            ),
        )
        radar["monitoring"]["last_scan_at"] = (
            latest.get("completed_at") or latest["started_at"]
        )
        radar["monitoring"]["next_scan_on"] = next_scan_on
        return payload

    return _mutate(
        workspace,
        operation="record_scan",
        payload={
            "scan": payload,
            "next_scan_on": next_scan_on,
            "selection_provenance": selection_provenance,
        },
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["monitoring"]["scan_history"], "scan_id", payload["scan_id"]
        ),
    )


def render_scan_worklist(workspace: Path, *, scan_id: str) -> Path:
    """Render direct-source work before the optional semantic web phase."""

    radar = load_validated_radar(workspace)
    scan = _find(
        radar["monitoring"]["scan_history"],
        "scan_id",
        safe_identifier(scan_id, field="scan_id"),
    )
    if scan["outcome"] != "running":
        raise ValueError("worklists are available only for running scans")
    entries = radar["source_plan"]["entries"]
    selection = scan["source_selection"]
    if selection["review_status"] != "confirmed":
        raise ValueError("worklist requires a confirmed query-scoped source selection")
    selected_ids = _selection_source_ids(selection)
    selected = [item for item in entries if item["source_id"] in selected_ids]
    if _source_registry_sha256(selected) != scan["source_plan_sha256"]:
        raise ValueError("selected source registry changed; restart the scan")
    if any(item["review_status"] != "confirmed" for item in selected):
        raise ValueError("selected source-plan review changed; restart the scan")
    priority = [
        item for item in entries if item["source_id"] in scan["priority_source_ids"]
    ]
    supplemental = [
        item
        for item in entries
        if item["source_id"] in selection["supplemental_source_ids"]
    ]
    lines = [
        f"# Source-first worklist — {scan['scan_id']}",
        "",
        f"Periodo: **{scan['window_start']} → {scan['window_end']}**",
        "",
        f"Territori richiesti: **{', '.join(scan['query_context']['territories'])}**",
        "",
        f"Categorie richieste: **{', '.join(scan['query_context']['categories'])}**",
        "",
        f"Selezione fonti: **{selection['review_status']}** · gap dichiarati: **{len(_scope_gap_keys(selection))}**",
        "",
        "## Copertura dichiarata della query",
        "",
        *_table(
            ["Dimensione", "Valore", "Stato", "Fonti", "Razionale"],
            [
                [
                    claim["dimension"],
                    claim["query_value"],
                    claim["status"],
                    ", ".join(claim["source_ids"]),
                    claim["rationale"],
                ]
                for claim in selection["scope_coverage"]
            ],
        ),
        "",
        f"Fonti prioritarie ancora da revisionare: **{', '.join(scan['unreviewed_priority_source_ids']) or 'nessuna'}**",
        "",
        "## 1. Fonti istituzionali prioritarie",
        "",
        *_table(
            ["Fonte", "Superficie", "Territori", "Categorie", "Atti", "URL", "Cursore"],
            [
                [
                    item["source_id"],
                    item["source_surface"],
                    ", ".join(item["territories"]),
                    ", ".join(item["categories"]),
                    ", ".join(item["act_families"]),
                    item["official_url"],
                    (
                        item["cursor_after"]["external_id"]
                        or item["cursor_after"]["publication_date"]
                        or item["cursor_after"]["official_url"]
                        if item["cursor_after"] is not None
                        else "prima scansione"
                    ),
                ]
                for item in priority
            ],
        ),
        "",
        "Controllare direttamente registro, albo/BUR, repository atti, allegati e aggiornamenti applicabili. Registrare ogni esito prima di proseguire.",
        "",
        "## 2. Fonti istituzionali supplementari",
        "",
        *_table(
            ["Fonte", "Superficie", "URL"],
            [
                [item["source_id"], item["source_surface"], item["official_url"]]
                for item in supplemental
            ],
        ),
        "",
        "## 3. Ricerca web semantica complementare",
        "",
        "Usarla solo dopo aver tentato tutte le fonti prioritarie. Non sostituisce un check diretto e non aumenta da sola la copertura del registro.",
        "",
    ]
    destination = (
        _radar_path(workspace).parent / f"source_first_worklist_{scan['scan_id']}.md"
    )
    return write_private_text(destination, "\n".join(lines))


def review_item(
    workspace: Path,
    *,
    scope: str,
    target_id: str,
    decision: str,
    reviewer_id: str,
    reviewer_role: str,
    confirmed_by_user: bool,
    idempotency_key: str,
    notes: str = "",
) -> dict[str, Any]:
    """Bind one explicit professional disposition to the exact proposed item."""

    if scope not in REVIEW_SCOPES or decision not in DECISIONS:
        raise ValueError("unsupported review scope or decision")
    if confirmed_by_user is not True:
        raise ValueError("explicit user confirmation is required")
    target_id = safe_identifier(target_id, field="target_id")
    reviewer_id = safe_identifier(reviewer_id, field="reviewer_id")
    if not str(reviewer_role).strip():
        raise ValueError("reviewer_role is required")
    operation_payload = {
        "scope": scope,
        "target_id": target_id,
        "decision": decision,
        "reviewer_id": reviewer_id,
        "reviewer_role": str(reviewer_role).strip(),
        "notes": str(notes).strip(),
    }

    def apply(radar: dict[str, Any]) -> dict[str, Any]:
        scan: dict[str, Any] | None = None
        if scope == "scan_source_selection":
            scan = _find(radar["monitoring"]["scan_history"], "scan_id", target_id)
            if scan["outcome"] != "running":
                raise ValueError("only a running scan selection can be reviewed")
            target = scan["source_selection"]
            if decision == "accepted":
                _validate_scan_source_selection(
                    selection=target,
                    query_context=scan["query_context"],
                    entries=radar["source_plan"]["entries"],
                    require_confirmed_sources=True,
                )
        else:
            collection, field = REVIEW_SCOPES[scope]
            items = (
                radar["source_plan"]["entries"]
                if collection == "source_plan"
                else radar[collection]
            )
            target = _find(items, field, target_id)
        if scope == "source_check" and target["check_status"] == "planned":
            raise ValueError("a planned source check cannot be professionally reviewed")
        target_sha256 = canonical_json_sha256(_review_basis(scope, target))
        new_status = {
            "accepted": "confirmed",
            "returned": "blocked",
            "rejected": "rejected",
        }[decision]
        if scope == "source_check":
            target["check_review_status"] = new_status
        else:
            target["review_status"] = new_status
        if scope == "profile":
            for facet in target["facets"]:
                facet["review_status"] = new_status
            for revision in target["revision_history"]:
                revision["review_status"] = new_status
        elif scope == "opportunity":
            for observation in target["lifecycle_history"]:
                observation["review_status"] = new_status
            for revision in target["revision_history"]:
                revision["review_status"] = new_status
        elif scope == "match" and target.get("economic_estimate") is not None:
            target["economic_estimate"]["review_status"] = new_status
        elif scope == "scan_source_selection":
            if scan is None:
                raise ValueError("scan source selection review requires a scan")
            selected_ids = set(scan["priority_source_ids"])
            unreviewed_priority_ids = sorted(
                item["source_id"]
                for item in radar["source_plan"]["entries"]
                if item["source_id"] in selected_ids
                and item["review_status"] != "confirmed"
            )
            scan["unreviewed_priority_source_ids"] = unreviewed_priority_ids
            scan["coverage"] = _scan_coverage(
                priority_source_ids=scan["priority_source_ids"],
                unreviewed_priority_source_ids=unreviewed_priority_ids,
                source_checks=[],
                selection_review_status=new_status,
                scope_gap_keys=_scope_gap_keys(target),
            )
        event = {
            "event_id": f"review-{len(radar['review_events']) + 1:04d}",
            "idempotency_key": safe_identifier(
                idempotency_key, field="idempotency_key"
            ),
            "scope": scope,
            "target_id": target_id,
            "target_sha256": target_sha256,
            "decision": decision,
            "reviewer_id": reviewer_id,
            "reviewer_role": str(reviewer_role).strip(),
            "confirmation_basis": "explicit_user_confirmation",
            "identity_assurance": "asserted_not_authenticated",
            "reviewed_at": iso_now(),
            "notes": str(notes).strip(),
        }
        radar["review_events"].append(event)
        return event

    return _mutate(
        workspace,
        operation="review",
        payload=operation_payload,
        idempotency_key=idempotency_key,
        mutation=apply,
        retry_result=lambda radar: _find(
            radar["review_events"], "idempotency_key", idempotency_key
        ),
    )


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    def cell(value: object) -> str:
        return (
            str(value if value not in (None, "") else "—")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(cell(value) for value in row) + " |" for row in rows),
    ]


def render_radar_report(workspace: Path) -> Path:
    """Render a concise operational radar from the validated workbench."""

    radar = load_validated_radar(workspace)
    coverage = radar["source_plan"]["coverage"]
    scans = radar["monitoring"]["scan_history"]
    latest_scan = scans[-1] if scans else None
    checks = (
        [
            entry
            for entry in radar["source_plan"]["entries"]
            if entry["last_scan_id"] == latest_scan["scan_id"]
        ]
        if latest_scan and latest_scan["outcome"] == "running"
        else latest_scan["source_check_snapshots"] if latest_scan else []
    )
    lines = [
        "# Vera — radar bandi e agevolazioni",
        "",
        "**BOZZA PER REVISIONE PROFESSIONALE — NESSUN CLIENTE CONTATTATO, NESSUNA DOMANDA INVIATA**",
        "",
        f"Radar: `{radar['radar_id']}` · ambito: `{radar['scope']}` · revisione: `{radar['revision']}` · data: `{radar['reference_date']}`",
        "",
        "## Stato corrente del registro fonti (non esito della scansione)",
        "",
        f"**{coverage['ratio_basis_points'] / 100:.2f}%** — {coverage['statement']}",
        "",
        *_table(
            [
                "Fonte",
                "Ruolo",
                "Superficie",
                "Livello",
                "Editore",
                "URL ufficiale",
                "Pertinenza e provenienza",
                "Stato",
                "Finestra",
                "Ultimo controllo",
                "Ultimo atto",
                "Risultati",
                "Revisione piano",
                "Revisione controllo",
            ],
            [
                [
                    item["source_id"],
                    item["discovery_role"],
                    item["source_surface"],
                    item["authority_level"],
                    item["publisher"],
                    item["official_url"],
                    item["relevance_rationale"],
                    item["check_status"],
                    (
                        f"{item['window_start']} → {item['window_end']}"
                        if item["window_start"]
                        else None
                    ),
                    item["checked_at"],
                    (
                        item["cursor_after"]["external_id"]
                        or item["cursor_after"]["publication_date"]
                        or item["cursor_after"]["official_url"]
                        if item["cursor_after"] is not None
                        else None
                    ),
                    item["result_count"],
                    item["review_status"],
                    item["check_review_status"],
                ]
                for item in radar["source_plan"]["entries"]
            ],
        ),
        "",
        "## Evidenza dell'ultima scansione",
        "",
        *(
            [
                f"Periodo controllato: **{latest_scan['window_start']} → {latest_scan['window_end']}**",
                "",
                f"Territori richiesti: **{', '.join(latest_scan['query_context']['territories'])}** · categorie: **{', '.join(latest_scan['query_context']['categories'])}**",
                "",
                f"Selezione fonti: **{latest_scan['source_selection']['review_status']}** · prioritarie: **{', '.join(latest_scan['source_selection']['priority_source_ids']) or 'nessuna'}** · supplementari: **{', '.join(latest_scan['source_selection']['supplemental_source_ids']) or 'nessuna'}**",
                "",
                *_table(
                    ["Dimensione query", "Valore", "Stato", "Fonti", "Motivazione"],
                    [
                        [
                            claim["dimension"],
                            claim["query_value"],
                            claim["status"],
                            ", ".join(claim["source_ids"]),
                            claim["rationale"],
                        ]
                        for claim in latest_scan["source_selection"]["scope_coverage"]
                    ],
                ),
                "",
                f"Esito: **{latest_scan['outcome']}** · copertura registro: **{latest_scan['coverage']['status']}** · ultimo controllo: **{latest_scan['coverage']['last_checked_at'] or '—'}**",
                "",
                latest_scan["source_selection"]["selection_rationale"],
                "",
                f"Gap di ambito: {', '.join(latest_scan['coverage']['uncovered_scope_keys']) or 'nessuno'}",
                "",
                f"Fonti controllate: {', '.join(latest_scan['source_ids']) or 'nessuna'}",
                "",
                f"Fonti prioritarie non verificate: {', '.join(latest_scan['coverage']['unverified_priority_source_ids']) or 'nessuna'}",
                "",
                f"Ricerca web complementare: **{latest_scan['semantic_web_check']['status']}**",
                "",
                latest_scan["coverage"]["statement"],
                "",
            ]
            if latest_scan is not None
            else ["Nessuna scansione temporale registrata.", ""]
        ),
        "## Inventari dei fascicoli nell'ultima scansione",
        "",
        *_table(
            [
                "Fonte",
                "Indici consultati",
                "Enumerato il",
                "Finestra",
                "Enumerazione completa",
                "Finestra vuota",
            ],
            [
                [
                    check["source_id"],
                    ", ".join(inventory["index_urls"]),
                    inventory["enumerated_at"],
                    f"{inventory['window_start']} → {inventory['window_end']}",
                    str(inventory["enumeration_complete"]),
                    inventory["empty_window_rationale"],
                ]
                for check in checks
                if (inventory := check.get("issue_inventory")) is not None
            ],
        ),
        "",
        "## Fascicoli controllati nell'ultima scansione",
        "",
        *_table(
            [
                "Fonte",
                "Fascicolo",
                "URL sommario",
                "Data pubblicazione",
                "Esito",
                "Verificato il",
                "Atti da esaminare",
                "Note",
            ],
            [
                [
                    check["source_id"],
                    issue["issue_id"],
                    issue["official_url"],
                    issue["publication_date"],
                    issue["status"],
                    issue["checked_at"],
                    ", ".join(issue["act_urls"]),
                    issue["notes"],
                ]
                for check in checks
                for issue in (check.get("issue_inventory") or {}).get("issues", [])
            ],
        ),
        "",
        "## Opportunità rilevate (anche senza abbinamenti)",
        "",
        *_table(
            ["Opportunità", "Titolo", "Stato", "Fonti", "Revisione"],
            [
                [
                    item["opportunity_id"],
                    item["official_title"],
                    item["current_lifecycle"],
                    ", ".join(item["source_ids"]),
                    item["review_status"],
                ]
                for item in radar["opportunities"]
            ],
        ),
        "",
        "## Opportunità e abbinamenti",
        "",
        *_table(
            [
                "Match",
                "Cliente",
                "Opportunità",
                "Compatibilità",
                "Stato bando",
                "Beneficio lordo",
                "Complessità",
                "Azione",
                "Revisione",
            ],
            [
                [
                    match["match_id"],
                    match["client_ref"],
                    match["opportunity_id"],
                    match["compatibility"],
                    _find(
                        radar["opportunities"],
                        "opportunity_id",
                        match["opportunity_id"],
                    )["current_lifecycle"],
                    (
                        f"{match['economic_estimate']['currency']} {match['economic_estimate']['gross_benefit_min']}–{match['economic_estimate']['gross_benefit_max']}"
                        if match["economic_estimate"]
                        else "non stimato"
                    ),
                    match["application_complexity"],
                    match["recommended_action"],
                    match["review_status"],
                ]
                for match in radar["matches"]
            ],
        ),
        "",
        "## Limiti",
        "",
        *(f"- {item}" for item in radar["limitations"]),
        "",
    ]
    report_path = _radar_path(workspace).parent / "opportunity_radar_review.md"
    return write_private_text(report_path, "\n".join(lines))


def _handoff_selection(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "client_ref": payload["client_ref"],
        "profile": payload["profile"],
        "profile_evidence": payload["profile_evidence"],
        "source_plan_entries": payload["source_plan_entries"],
        "opportunity": payload["opportunity"],
        "match": payload["match"],
        "coverage": payload["coverage"],
    }


def validate_opportunity_handoff_payload(
    payload: dict[str, Any], *, expected_client_ref: str | None = None
) -> None:
    """Verify one handoff entirely from the bytes available to its consumer."""

    issues = validate_artifact_schema("opportunity_handoff", payload)
    if issues:
        first = issues[0]
        raise ValueError(f"{first['path']}: {first['message']}")
    if expected_client_ref is not None and payload["client_ref"] != expected_client_ref:
        raise ValueError("opportunity handoff belongs to another client reference")
    profile = payload["profile"]
    opportunity = payload["opportunity"]
    match = payload["match"]
    if (
        profile["client_ref"] != payload["client_ref"]
        or match["client_ref"] != payload["client_ref"]
    ):
        raise ValueError("opportunity handoff client references do not close")
    if match["opportunity_id"] != opportunity["opportunity_id"]:
        raise ValueError("opportunity handoff match references another opportunity")

    evidence = payload["profile_evidence"]
    evidence_ids = _unique_ids(evidence, "evidence_id")
    if any(item["client_ref"] != payload["client_ref"] for item in evidence):
        raise ValueError("opportunity handoff includes another client's evidence")
    facet_ids = _unique_ids(profile["facets"], "facet_id")
    referenced_evidence = {
        evidence_id
        for facet in profile["facets"]
        for evidence_id in facet["evidence_refs"]
    } | {
        evidence_id
        for revision in profile["revision_history"]
        for evidence_id in revision["evidence_refs"]
    }
    if referenced_evidence - evidence_ids:
        raise ValueError("opportunity handoff profile evidence is not reference-closed")
    if set(match["profile_facet_ids"]) - facet_ids:
        raise ValueError("opportunity handoff match facets are not reference-closed")

    sources = payload["source_plan_entries"]
    source_ids = _unique_ids(sources, "source_id")
    for source in sources:
        _validate_issue_inventory(source)
    used_sources = set(opportunity["source_ids"]) | set(match["source_ids"])
    if used_sources - source_ids:
        raise ValueError("opportunity handoff sources are not reference-closed")
    if any(
        set(item["source_ids"]) - source_ids
        for item in opportunity["lifecycle_history"]
    ):
        raise ValueError(
            "opportunity handoff lifecycle sources are not reference-closed"
        )
    if any(
        set(item["source_ids"]) - source_ids for item in opportunity["revision_history"]
    ):
        raise ValueError(
            "opportunity handoff revision sources are not reference-closed"
        )
    if payload["coverage"] != _coverage(sources):
        raise ValueError("opportunity handoff coverage does not reproduce")
    if payload["source_entries_sha256"] != canonical_json_sha256(sources):
        raise ValueError("opportunity handoff source-entry hash does not reproduce")
    if payload["selection_sha256"] != canonical_json_sha256(
        _handoff_selection(payload)
    ):
        raise ValueError("opportunity handoff selection hash does not reproduce")
    if match.get("economic_estimate") is not None:
        _validate_economic_estimate(
            match["economic_estimate"], path="match.economic_estimate"
        )


def create_handoff(
    workspace: Path,
    *,
    match_id: str,
    output_path: Path,
) -> Path:
    """Seal one confirmed radar match for import into a client-bound dossier run."""

    radar = load_validated_radar(workspace)
    match = _find(
        radar["matches"], "match_id", safe_identifier(match_id, field="match_id")
    )
    opportunity = _find(
        radar["opportunities"], "opportunity_id", match["opportunity_id"]
    )
    profile = _find(radar["profiles"], "client_ref", match["client_ref"])
    if any(
        item["review_status"] != "confirmed" for item in (match, opportunity, profile)
    ):
        raise ValueError(
            "profile, opportunity and match must be professionally confirmed"
        )
    used_source_ids = set(opportunity["source_ids"]) | set(match["source_ids"])
    sources = radar["source_plan"]["entries"]
    selected_sources = [
        item for item in sources if item["source_id"] in used_source_ids
    ]
    if any(
        item["review_status"] != "confirmed"
        or item["check_status"] != "checked"
        or item["check_review_status"] != "confirmed"
        for item in selected_sources
    ) or len(selected_sources) != len(used_source_ids):
        raise ValueError(
            "all handoff sources must be checked and professionally confirmed"
        )
    evidence_ids = {
        evidence_id
        for facet in profile["facets"]
        for evidence_id in facet["evidence_refs"]
    } | {
        evidence_id
        for revision in profile["revision_history"]
        for evidence_id in revision["evidence_refs"]
    }
    selected_evidence = [
        item
        for item in radar["profile_evidence"]
        if item["evidence_id"] in evidence_ids
    ]
    if len(selected_evidence) != len(evidence_ids) or any(
        item["review_status"] != "confirmed" for item in selected_evidence
    ):
        raise ValueError("all referenced profile evidence must be confirmed")
    selected_coverage = _coverage(selected_sources)
    payload = {
        "schema_version": "3.0",
        "plugin": PLUGIN_NAME,
        "radar_id": radar["radar_id"],
        "radar_revision": radar["revision"],
        "created_at": iso_now(),
        "client_ref": match["client_ref"],
        "profile": profile,
        "profile_evidence": selected_evidence,
        "source_plan_entries": selected_sources,
        "opportunity": opportunity,
        "match": match,
        "coverage": selected_coverage,
        "source_entries_sha256": canonical_json_sha256(selected_sources),
        "selection_sha256": "",
        "limitations": [
            "This handoff selects an opportunity for a new client-bound application review; it is not an eligibility decision.",
            "The application workflow must register and review the exact official call, amendments, annexes, FAQs and client evidence.",
            "Source-first scan coverage proves execution of the reviewed registry only; it is not a statistical completeness claim.",
            "No authentication, client contact, signature, save or submission action has been performed.",
        ],
    }
    payload["selection_sha256"] = canonical_json_sha256(_handoff_selection(payload))
    validate_opportunity_handoff_payload(payload)
    destination = output_path.expanduser().resolve()
    workspace_root = _radar_path(workspace).parent
    try:
        destination.relative_to(workspace_root)
    except ValueError as exc:
        raise PermissionError(
            "handoff output must remain inside the radar workspace"
        ) from exc
    return write_private_json(destination, payload)


def _load_payload(path: Path) -> dict[str, Any]:
    return load_json_object(path.expanduser().resolve())


def _add_contribution_arguments(
    parser: argparse.ArgumentParser, *, required: bool = True
) -> None:
    parser.add_argument(
        "--origin",
        required=required,
        choices=[
            "model_suggested",
            "user_supplied",
            "document_observation",
            "mechanical_observation",
        ],
    )
    parser.add_argument("--provider", required=required)
    parser.add_argument("--model", required=required)
    parser.add_argument("--prompt-template-version", required=required)
    parser.add_argument("--recorded-by", required=required)
    parser.add_argument("--model-session-ref")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize = subparsers.add_parser("initialize")
    initialize.add_argument("--radar-id", required=True)
    initialize.add_argument("--workspace-id", required=True)
    initialize.add_argument("--reference-date", required=True)
    initialize.add_argument(
        "--scope", required=True, choices=["single_client", "portfolio"]
    )
    initialize.add_argument("--authorized-by", required=True)
    initialize.add_argument("--retention-owner", required=True)
    initialize.add_argument("--confirmed-by-user", action="store_true")
    for command in (
        "record-evidence",
        "record-profile",
        "record-source",
        "record-opportunity",
        "record-match",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--input", required=True, type=Path)
        child.add_argument("--idempotency-key", required=True)
        _add_contribution_arguments(child)
    source_check = subparsers.add_parser("record-source-check")
    source_check.add_argument("--source-id", required=True)
    source_check.add_argument("--check-id", required=True)
    source_check.add_argument("--scan-id", required=True)
    source_check.add_argument(
        "--check-status", required=True, choices=sorted(CHECK_STATUSES - {"planned"})
    )
    source_check.add_argument("--checked-at", required=True)
    source_check.add_argument("--window-start", required=True)
    source_check.add_argument("--window-end", required=True)
    source_check.add_argument("--next-check-on")
    source_check.add_argument("--result-count", type=int)
    source_check.add_argument("--error-code")
    source_check.add_argument("--cursor-input", type=Path)
    source_check.add_argument("--issue-inventory-input", type=Path)
    source_check.add_argument("--idempotency-key", required=True)
    scan = subparsers.add_parser("record-scan")
    scan.add_argument("--input", required=True, type=Path)
    scan.add_argument("--next-scan-on")
    scan.add_argument("--idempotency-key", required=True)
    _add_contribution_arguments(scan, required=False)
    worklist = subparsers.add_parser("worklist")
    worklist.add_argument("--scan-id", required=True)
    review = subparsers.add_parser("review")
    review.add_argument("--scope", required=True, choices=sorted(REVIEW_SCOPES))
    review.add_argument("--target-id", required=True)
    review.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--reviewer-role", required=True)
    review.add_argument("--notes", default="")
    review.add_argument("--confirmed-by-user", action="store_true")
    review.add_argument("--idempotency-key", required=True)
    subparsers.add_parser("report")
    handoff = subparsers.add_parser("handoff")
    handoff.add_argument("--match-id", required=True)
    handoff.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    common = {
        "workspace": args.workspace,
        "idempotency_key": getattr(args, "idempotency_key", ""),
    }
    if args.command == "initialize":
        path = initialize_radar(
            args.workspace,
            radar_id=args.radar_id,
            workspace_id=args.workspace_id,
            reference_date=args.reference_date,
            scope=args.scope,
            authorized_by=args.authorized_by,
            retention_owner=args.retention_owner,
            confirmed_by_user=args.confirmed_by_user,
        )
    elif args.command in {
        "record-evidence",
        "record-profile",
        "record-source",
        "record-opportunity",
        "record-match",
    }:
        function = {
            "record-evidence": record_profile_evidence,
            "record-profile": record_profile,
            "record-source": record_source,
            "record-opportunity": record_opportunity,
            "record-match": record_match,
        }[args.command]
        argument_name = (
            "evidence"
            if args.command == "record-evidence"
            else args.command.removeprefix("record-").replace("-", "_")
        )
        result = function(
            **common,
            **{argument_name: _load_payload(args.input)},
            origin=args.origin,
            provider=args.provider,
            model=args.model,
            prompt_template_version=args.prompt_template_version,
            recorded_by=args.recorded_by,
            model_session_ref=args.model_session_ref,
        )
        path = _radar_path(args.workspace)
        LOGGER.info("Recorded %s", result)
    elif args.command == "record-source-check":
        record_source_check(
            **common,
            source_id=args.source_id,
            check_id=args.check_id,
            scan_id=args.scan_id,
            check_status=args.check_status,
            checked_at=args.checked_at,
            window_start=args.window_start,
            window_end=args.window_end,
            next_check_on=args.next_check_on,
            result_count=args.result_count,
            error_code=args.error_code,
            cursor_after=(
                _load_payload(args.cursor_input) if args.cursor_input else None
            ),
            issue_inventory=(
                _load_payload(args.issue_inventory_input)
                if args.issue_inventory_input
                else None
            ),
        )
        path = _radar_path(args.workspace)
    elif args.command == "record-scan":
        record_scan(
            **common,
            scan=_load_payload(args.input),
            next_scan_on=args.next_scan_on,
            origin=args.origin,
            provider=args.provider,
            model=args.model,
            prompt_template_version=args.prompt_template_version,
            recorded_by=args.recorded_by,
            model_session_ref=args.model_session_ref,
        )
        path = _radar_path(args.workspace)
    elif args.command == "worklist":
        path = render_scan_worklist(args.workspace, scan_id=args.scan_id)
    elif args.command == "review":
        review_item(
            **common,
            scope=args.scope,
            target_id=args.target_id,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewer_role=args.reviewer_role,
            confirmed_by_user=args.confirmed_by_user,
            notes=args.notes,
        )
        path = _radar_path(args.workspace)
    elif args.command == "report":
        path = render_radar_report(args.workspace)
    else:
        path = create_handoff(
            args.workspace, match_id=args.match_id, output_path=args.output
        )
    LOGGER.info("%s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
