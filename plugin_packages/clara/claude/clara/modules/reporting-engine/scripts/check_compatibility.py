"""Check manifest-to-dataset compatibility using only mechanical evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

__all__ = [
    "audit_manifest_against_dataset_profile",
    "check_capability_compatibility",
    "check_profile_compatibility",
    "main",
]

REPORTING_ENGINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPORTING_ENGINE_ROOT / "catalog" / "selection_manifest.json"

SEMANTIC_OR_PACKAGE_ISSUES = {
    "requires_semantic_or_package_metric_source",
    "requires_semantic_or_package_role",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _columns_by_role(profile: dict[str, Any], role: str) -> list[str]:
    return list((profile.get("roles") or {}).get(role) or [])


def _role_candidate_columns(profile: dict[str, Any], role: str) -> list[str]:
    flattened = (profile.get("role_candidate_columns") or {}).get(role) or []
    if flattened:
        return [str(column) for column in flattened]
    candidates = (profile.get("role_candidates") or {}).get(role) or []
    columns: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("column"):
            columns.append(str(candidate["column"]))
        elif isinstance(candidate, str):
            columns.append(candidate)
    return columns


def _metric_candidates(
    profile: dict[str, Any], source_metric_role: dict[str, Any]
) -> list[str]:
    metric_classes = profile.get("metric_classes") or {}
    candidates: list[str] = []
    for metric_class in source_metric_role.get("accepted_metric_classes") or []:
        for column in metric_classes.get(metric_class) or []:
            if column not in candidates:
                candidates.append(column)
    return candidates


def _column_profile(profile: dict[str, Any], column: str) -> dict[str, Any]:
    columns = profile.get("columns") or {}
    value = columns.get(column)
    return value if isinstance(value, dict) else {}


def _candidate_available_rows(
    profile: dict[str, Any], column: str, dataset_row_count: int
) -> int:
    column_profile = _column_profile(profile, column)
    if column_profile:
        return dataset_row_count - int(column_profile.get("null_count") or 0)
    derived = (profile.get("derived_metrics") or {}).get(column) or {}
    produced_from = [str(value) for value in derived.get("produced_from") or []]
    if not produced_from:
        return 0
    source_rows = [
        dataset_row_count - int(_column_profile(profile, source).get("null_count") or 0)
        for source in produced_from
        if _column_profile(profile, source)
    ]
    return min(source_rows) if len(source_rows) == len(produced_from) else 0


def _rejection_record(
    profile: dict[str, Any], column: str, reason: str
) -> dict[str, Any]:
    column_profile = _column_profile(profile, column)
    return {
        "column": column,
        "reason": reason,
        "source_role": column_profile.get("role"),
        "metric_class": column_profile.get("metric_class"),
        "cardinality_class": column_profile.get("cardinality_class"),
        "null_ratio": column_profile.get("null_ratio"),
        "period_parseability": column_profile.get("period_parseability"),
    }


def _metric_rejections(
    profile: dict[str, Any],
    *,
    accepted_metric_classes: list[str],
    matched_columns: list[str],
    limit: int = 20,
) -> dict[str, Any]:
    accepted = set(accepted_metric_classes)
    matched = set(matched_columns)
    rejected: list[dict[str, Any]] = []
    for column in _columns_by_role(profile, "metric"):
        if column in matched:
            continue
        metric_class = _column_profile(profile, column).get("metric_class")
        reason = (
            "metric_class_not_accepted"
            if metric_class not in accepted
            else "not_selected_after_candidate_limit"
        )
        rejected.append(_rejection_record(profile, column, reason))
    for column, derived_profile in (profile.get("derived_metrics") or {}).items():
        if column in matched:
            continue
        metric_class = derived_profile.get("metric_class")
        reason = (
            "metric_class_not_accepted"
            if metric_class not in accepted
            else "not_selected_after_candidate_limit"
        )
        rejected.append(
            {
                "column": column,
                "reason": reason,
                "source_role": "derived_metric",
                "metric_class": metric_class,
                "cardinality_class": "derived",
                "null_ratio": None,
                "period_parseability": None,
            }
        )
    return {
        "rejected_count": len(rejected),
        "samples": rejected[:limit],
    }


def _period_rejections(
    profile: dict[str, Any], *, matched_columns: list[str], limit: int = 20
) -> dict[str, Any]:
    matched = set(matched_columns)
    rejected = []
    for column, column_profile in (profile.get("columns") or {}).items():
        if column in matched:
            continue
        if column_profile.get("role") == "period":
            reason = "not_selected_after_candidate_limit"
        elif (column_profile.get("period_parseability") or {}).get("is_parseable"):
            reason = "parseable_but_not_classified_as_period"
        else:
            reason = "not_parseable_as_period"
        rejected.append(_rejection_record(profile, str(column), reason))
    return {
        "rejected_count": len(rejected),
        "samples": rejected[:limit],
    }


def _dimension_rejections(
    profile: dict[str, Any],
    *,
    role: str,
    role_resolution: dict[str, Any],
    matched_columns: list[str],
    limit: int = 20,
) -> dict[str, Any]:
    matched = set(matched_columns)
    resolution_type = str(role_resolution.get("resolution_type") or "")
    if resolution_type == "semantic_or_package_role":
        return {
            "rejected_count": 0,
            "samples": [],
            "not_applicable_reason": "requires_semantic_or_package_role",
        }
    required_profile_roles = set(role_resolution.get("required_profile_roles") or [])
    rejected: list[dict[str, Any]] = []
    candidate_columns = _columns_by_role(profile, "dimension") + _columns_by_role(
        profile, "identifier"
    )
    for column in dict.fromkeys(candidate_columns):
        if column in matched:
            continue
        if resolution_type == "schema_role" and required_profile_roles:
            reason = "does_not_match_required_profile_role"
        elif resolution_type == "direct_rank_or_lane":
            reason = "does_not_match_rank_or_lane_profile_role"
        elif role in {"point_dimension", "product"}:
            reason = "not_selected_as_entity_or_point_dimension"
        else:
            reason = "not_selected_after_role_token_ranking"
        rejected.append(_rejection_record(profile, column, reason))
    return {
        "rejected_count": len(rejected),
        "samples": rejected[:limit],
    }


def _normalize_token(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _special_dimension_candidates(profile: dict[str, Any], role: str) -> list[str]:
    target = _normalize_token(role)
    candidates = []
    for column in _columns_by_role(profile, "dimension"):
        normalized = _normalize_token(column)
        if target in normalized or normalized in target:
            candidates.append(column)
    return candidates


def _direct_dimension_candidates(profile: dict[str, Any], role: str) -> list[str]:
    if role in {"point_dimension", "product"}:
        columns = _role_candidate_columns(profile, "entity_key") + _columns_by_role(
            profile, "dimension"
        )
    else:
        columns = _columns_by_role(profile, "dimension") + _columns_by_role(
            profile, "identifier"
        )
    columns = list(dict.fromkeys(columns))
    target = role.casefold()
    role_tokens = [
        _normalize_token(token)
        for token in target.split("_")
        if token not in {"category", "dimension", "driver", "item", "member", "point"}
    ]
    matches: list[str] = []
    for column in columns:
        column_tokens = {
            _normalize_token(token) for token in column.casefold().split("_")
        }
        column_tokens.add(_normalize_token(column))
        if any(token and token in column_tokens for token in role_tokens):
            matches.append(column)
    fallback = [column for column in columns if column not in matches]
    return (matches + fallback)[:30]


def _profile_role_candidates(profile: dict[str, Any], profile_role: str) -> list[str]:
    if profile_role == "period":
        return _columns_by_role(profile, "period")
    if profile_role == "direct_dimension":
        return _role_candidate_columns(profile, "direct_dimension") or _columns_by_role(
            profile, "dimension"
        )
    if profile_role in {
        "entity_key",
        "ordered_stage",
        "rank_or_lane",
        "set_dimension",
        "set_item",
        "statement_line_item",
        "statement_scenario",
    }:
        return _role_candidate_columns(profile, profile_role)
    return []


def _resolve_dimension_role(
    profile: dict[str, Any], role: str, requirement: dict[str, Any]
) -> dict[str, Any]:
    """Validate explicit role prerequisites without making semantic choices."""

    resolution_type = str(requirement.get("resolution_type") or "direct_dimension")
    required_profile_roles = list(requirement.get("requires_profile_roles") or [])
    prerequisite_matches = {
        profile_role: _profile_role_candidates(profile, profile_role)
        for profile_role in required_profile_roles
    }
    missing_profile_roles = [
        profile_role
        for profile_role, candidates in prerequisite_matches.items()
        if not candidates
    ]
    minimum_candidate_count = int(requirement.get("minimum_candidate_count") or 0)
    candidate_count_role = str(
        requirement.get("candidate_count_profile_role") or "direct_dimension"
    )
    available_candidate_count = len(
        prerequisite_matches.get(candidate_count_role) or []
    )
    candidate_columns = set(prerequisite_matches.get("direct_dimension") or [])
    multidimensional_relationships = [
        relationship
        for relationship in profile.get("dimension_relationships") or []
        if relationship.get("left_column") in candidate_columns
        and relationship.get("right_column") in candidate_columns
        and bool(relationship.get("supports_multidimensional_path"))
    ]
    requires_non_bijective_pair = bool(
        requirement.get("requires_non_bijective_dimension_pair", False)
    )
    if resolution_type == "direct_dimension":
        candidates = _direct_dimension_candidates(profile, role)
    elif resolution_type == "direct_rank_or_lane":
        candidates = _profile_role_candidates(profile, "rank_or_lane")
    elif resolution_type == "schema_role":
        profile_role = required_profile_roles[0] if required_profile_roles else role
        candidates = _profile_role_candidates(profile, profile_role)
    elif resolution_type == "semantic_or_package_role":
        candidates = []
        missing_profile_roles = required_profile_roles or ["semantic_or_package_role"]
    else:
        candidates = []

    issues: list[str] = []
    if resolution_type == "semantic_or_package_role":
        issues.append("requires_semantic_or_package_role")
    elif missing_profile_roles:
        if resolution_type == "schema_role":
            issues.append("missing_schema_role")
        else:
            issues.append("missing_role_prerequisites")
    elif minimum_candidate_count > available_candidate_count:
        issues.append("insufficient_role_prerequisites")
    elif requires_non_bijective_pair and not multidimensional_relationships:
        issues.append("no_non_redundant_dimension_pair")
    elif (
        resolution_type
        in {
            "direct_dimension",
            "direct_rank_or_lane",
            "schema_role",
        }
        and not candidates
    ):
        issues.append("missing_role_candidates")

    return {
        "role": role,
        "required": bool(requirement.get("required", True)),
        "resolution_type": resolution_type,
        "required_profile_roles": required_profile_roles,
        "missing_profile_roles": missing_profile_roles,
        "minimum_candidate_count": minimum_candidate_count,
        "candidate_count_profile_role": candidate_count_role,
        "available_candidate_count": available_candidate_count,
        "requires_non_bijective_dimension_pair": requires_non_bijective_pair,
        "multidimensional_relationship_evidence": multidimensional_relationships[:20],
        "candidate_columns": candidates[:20],
        "prerequisite_matches": {
            key: values[:20] for key, values in prerequisite_matches.items()
        },
        "issues": issues,
        "notes": requirement.get("notes"),
    }


def _derived_metric_package_issues(
    metric_requirements: dict[str, Any],
) -> list[str]:
    for role in metric_requirements.get("derived_metric_roles") or []:
        produced_from = role.get("produced_from") or []
        if "attribute_evidence_package" in produced_from:
            return ["requires_semantic_or_package_metric_source"]
    return []


def _period_scope_preflight(
    period_requirements: dict[str, Any],
    period_columns: list[str],
) -> dict[str, Any]:
    """Expose period-scope requirements without making semantic choices."""

    scope_contract = period_requirements.get("scope_contract") or {}
    role = str(scope_contract.get("role") or period_requirements.get("role") or "none")
    period_column_required = bool(
        period_requirements.get(
            "required", scope_contract.get("period_column_required", role != "none")
        )
    )
    scope_required = bool(
        scope_contract.get("scope_required_for_render", role == "filter")
    )
    explicit_all_data_allowed = bool(
        scope_contract.get("explicit_all_data_allowed", role == "filter")
    )
    if role == "none":
        status = "not_applicable"
        warning = ""
    elif not period_columns:
        if period_column_required:
            status = "blocked_missing_period_column"
            warning = "No required period column candidate is available."
        else:
            status = "optional_filter_unavailable_all_data_only"
            warning = (
                "No optional period column candidate is available; this chart "
                "can still render all records without period filtering."
            )
    elif scope_required:
        status = "caller_scope_required_before_render"
        warning = (
            "This chart has a period filter. A caller must pass a bounded "
            "analysis period or explicitly request all available data."
        )
    elif role in {"axis", "axis_or_table"}:
        status = "scope_optional_available_period_axis"
        warning = (
            "This chart can use the available period axis; bounded questions "
            "should still pass an explicit period scope."
        )
    else:
        status = "scope_optional"
        warning = ""
    return {
        "role": role,
        "status": status,
        "period_column_required": period_column_required,
        "scope_required_for_render": scope_required,
        "explicit_all_data_allowed": explicit_all_data_allowed,
        "accepted_scope_controls": list(
            scope_contract.get("accepted_scope_controls") or []
        ),
        "period_candidates": period_columns[:20],
        "unscoped_default": scope_contract.get("unscoped_default"),
        "pre_render_warning": warning,
    }


def _capability_profile_match(
    capability: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    contract = capability["selection_contract"]
    requirements = contract["dataset_requirements"]
    metric_requirements = requirements["metrics"]
    period_requirements = requirements["period"]
    dimension_requirements = requirements["dimensions"]
    observation_requirements = requirements.get("observations") or {
        "minimum_non_null_rows": 1,
        "scope": "rendered_analysis_scope",
    }
    source_metric_matches = []
    missing_source_metric_roles = []
    mechanical_role_matches: list[dict[str, Any]] = []
    rejected_column_evidence: list[dict[str, Any]] = []
    for source_metric_role in metric_requirements["source_metric_roles"]:
        role_required = bool(source_metric_role.get("required", True))
        candidates = _metric_candidates(profile, source_metric_role)
        accepted_metric_classes = (
            source_metric_role.get("accepted_metric_classes") or []
        )
        source_metric_matches.append(
            {
                "role": source_metric_role["role"],
                "required": role_required,
                "accepted_metric_classes": accepted_metric_classes,
                "candidate_columns": candidates,
            }
        )
        if role_required and not candidates:
            missing_source_metric_roles.append(source_metric_role["role"])
        mechanical_role_matches.append(
            _mechanical_role_match(
                kind="metric",
                role=str(source_metric_role["role"]),
                candidate_columns=candidates,
                required=role_required,
                issue=(
                    "missing_source_metric_role"
                    if role_required and not candidates
                    else None
                ),
                accepted_metric_classes=accepted_metric_classes,
            )
        )
        rejected_column_evidence.append(
            {
                "kind": "metric",
                "role": str(source_metric_role["role"]),
                **_metric_rejections(
                    profile,
                    accepted_metric_classes=list(accepted_metric_classes),
                    matched_columns=candidates,
                ),
            }
        )

    period_columns = _columns_by_role(profile, "period")
    period_role = str(period_requirements.get("role") or "none")
    period_required = bool(period_requirements.get("required", period_role != "none"))
    minimum_distinct_period_values = int(
        period_requirements.get("minimum_distinct_values") or 0
    )
    period_value_evidence = [
        {
            "column": column,
            "distinct_count": int(
                ((profile.get("columns") or {}).get(column) or {}).get("distinct_count")
                or 0
            ),
            "ordered_values": list(
                ((profile.get("columns") or {}).get(column) or {}).get("ordered_values")
                or []
            )[:20],
        }
        for column in period_columns
    ]
    available_distinct_period_values = max(
        (item["distinct_count"] for item in period_value_evidence), default=0
    )
    period_scope = _period_scope_preflight(period_requirements, period_columns)
    period_scope.update(
        {
            "comparison_pair_required": bool(
                period_requirements.get("comparison_pair_required", False)
            ),
            "minimum_distinct_period_values": minimum_distinct_period_values,
            "available_distinct_period_values": available_distinct_period_values,
            "period_value_evidence": period_value_evidence,
        }
    )
    if period_role in {"axis", "axis_or_table", "filter"}:
        mechanical_role_matches.append(
            _mechanical_role_match(
                kind="period",
                role="period_axis" if period_role != "filter" else "period_filter",
                candidate_columns=period_columns,
                required=period_required,
                issue=(
                    "missing_period_role"
                    if period_required and not period_columns
                    else None
                ),
                period_role=period_role,
            )
        )
        rejected_column_evidence.append(
            {
                "kind": "period",
                "role": "period_axis" if period_role != "filter" else "period_filter",
                **_period_rejections(profile, matched_columns=period_columns),
            }
        )
    required_dimension_count = dimension_requirements.get("minimum_count", 0)
    dimension_columns = _columns_by_role(profile, "dimension")
    required_dimension_roles = dimension_requirements["required_roles"]
    optional_dimension_roles = dimension_requirements.get("optional_roles") or []
    all_dimension_roles = [*required_dimension_roles, *optional_dimension_roles]
    role_requirements = dimension_requirements.get("role_requirements") or {
        role: {
            "role": role,
            "required": role in required_dimension_roles,
            "resolution_type": "direct_dimension",
            "requires_profile_roles": ["direct_dimension"],
        }
        for role in all_dimension_roles
    }
    role_resolutions = [
        _resolve_dimension_role(profile, role, role_requirements.get(role, {}))
        for role in all_dimension_roles
    ]
    dimension_contract = dimension_requirements.get("dimension_contract") or {}
    requires_non_bijective_dimension_pair = bool(
        dimension_contract.get("requires_non_bijective_dimension_pair", False)
    )
    non_bijective_dimension_pairs = [
        relationship
        for relationship in profile.get("dimension_relationships") or []
        if relationship.get("supports_multidimensional_path")
    ]
    mechanical_role_matches.extend(
        _dimension_role_match(role_resolution) for role_resolution in role_resolutions
    )
    for role_resolution in role_resolutions:
        rejected_column_evidence.append(
            {
                "kind": "dimension",
                "role": str(role_resolution["role"]),
                **_dimension_rejections(
                    profile,
                    role=str(role_resolution["role"]),
                    role_resolution=role_resolution,
                    matched_columns=list(role_resolution.get("candidate_columns") or [])
                    + [
                        str(value)
                        for values in (
                            role_resolution.get("prerequisite_matches") or {}
                        ).values()
                        for value in values
                    ],
                ),
            }
        )
    issues = []
    if missing_source_metric_roles:
        issues.append("missing_source_metric_roles")
    if period_required and not period_columns:
        issues.append("missing_required_period_column")
    if (
        minimum_distinct_period_values > 0
        and available_distinct_period_values < minimum_distinct_period_values
    ):
        issues.append("insufficient_distinct_period_values")
    if len(dimension_columns) < required_dimension_count:
        issues.append("insufficient_dimension_columns")
    for role_resolution in role_resolutions:
        if not role_resolution.get("required", True):
            continue
        issues.extend(role_resolution["issues"])
    if requires_non_bijective_dimension_pair and not non_bijective_dimension_pairs:
        issues.append("no_non_redundant_dimension_pair")
    raw_dataset_row_count = profile.get("row_count")
    observation_count_known = isinstance(raw_dataset_row_count, int)
    dataset_row_count = int(raw_dataset_row_count) if observation_count_known else None
    metric_role_available_rows = (
        {
            str(match["role"]): max(
                (
                    _candidate_available_rows(profile, column, int(dataset_row_count))
                    for column in match["candidate_columns"]
                ),
                default=0,
            )
            for match in source_metric_matches
            if match.get("required", True)
        }
        if observation_count_known
        else {}
    )
    available_observation_rows = (
        min(metric_role_available_rows.values())
        if metric_role_available_rows
        else dataset_row_count
    )
    minimum_observation_rows = int(
        observation_requirements.get("minimum_non_null_rows") or 1
    )
    if (
        available_observation_rows is not None
        and available_observation_rows < minimum_observation_rows
    ):
        issues.append("insufficient_observation_rows")
    issues.extend(_derived_metric_package_issues(metric_requirements))
    issues = sorted(set(issues))

    status = "mechanically_compatible" if not issues else "mechanically_incomplete"
    return {
        "capability_id": capability["capability_id"],
        "status": status,
        "issues": issues,
        "selection_emphasis": capability["selection_emphasis"],
        "source_metric_matches": source_metric_matches,
        "derived_metric_roles": [
            role["role"] for role in metric_requirements["derived_metric_roles"]
        ],
        "period_candidates": period_columns,
        "period_scope": period_scope,
        "required_dimension_count": required_dimension_count,
        "observation_evidence": {
            "required_minimum_non_null_rows": minimum_observation_rows,
            "available_dataset_rows": dataset_row_count,
            "available_rows_by_required_metric_role": metric_role_available_rows,
            "available_observation_rows": available_observation_rows,
            "observation_count_known": observation_count_known,
            "requirement_scope": observation_requirements.get("scope"),
            "scope_warning": (
                "A selected period or filter must retain at least the required "
                "number of non-null rows. Dataset-wide compatibility does not "
                "prove every narrower scope is renderable."
            ),
        },
        "required_dimension_roles": required_dimension_roles,
        "optional_dimension_roles": optional_dimension_roles,
        "dimension_pair_evidence": {
            "required": requires_non_bijective_dimension_pair,
            "status": (
                "available"
                if non_bijective_dimension_pairs
                else (
                    "missing"
                    if requires_non_bijective_dimension_pair
                    else "not_required"
                )
            ),
            "candidate_pairs": non_bijective_dimension_pairs[:20],
        },
        "mechanical_role_matches": mechanical_role_matches,
        "rejected_column_evidence": rejected_column_evidence,
        "unmatched_required_roles": [
            {
                "kind": match["kind"],
                "role": match["role"],
                "issue": match.get("issue"),
            }
            for match in mechanical_role_matches
            if match["required"] and match["fit_status"] != "satisfied"
        ],
        "ambiguous_required_roles": [
            {
                "kind": match["kind"],
                "role": match["role"],
                "candidate_count": match["candidate_count"],
                "candidate_columns": match["candidate_columns"][:8],
            }
            for match in mechanical_role_matches
            if match["required"] and match["ambiguity_status"] == "ambiguous"
        ],
        "unavailable_optional_roles": [
            {
                "kind": match["kind"],
                "role": match["role"],
                "issue": match.get("issue"),
            }
            for match in mechanical_role_matches
            if not match["required"] and match["fit_status"] == "optional_not_matched"
        ],
        "ambiguous_available_roles": [
            {
                "kind": match["kind"],
                "role": match["role"],
                "required": match["required"],
                "candidate_count": match["candidate_count"],
                "candidate_columns": match["candidate_columns"][:8],
            }
            for match in mechanical_role_matches
            if match["ambiguity_status"] == "ambiguous"
        ],
        "special_dimension_matches": {
            role: _special_dimension_candidates(profile, role)
            for role in all_dimension_roles
        },
        "role_resolutions": role_resolutions,
        "dimension_candidates_sample": dimension_columns[:20],
        "analysis_validity_status": "not_checked",
    }


def _mechanical_role_match(
    *,
    kind: str,
    role: str,
    candidate_columns: list[str],
    required: bool,
    issue: str | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    candidate_columns = list(dict.fromkeys(candidate_columns))
    candidate_count = len(candidate_columns)
    if issue:
        fit_status = "missing"
    elif candidate_count:
        fit_status = "satisfied"
    elif required:
        fit_status = "missing"
        issue = "missing_required_role"
    else:
        fit_status = "optional_not_matched"
    ambiguity_status = "ambiguous" if candidate_count > 1 else "unambiguous"
    return {
        "kind": kind,
        "role": role,
        "required": required,
        "fit_status": fit_status,
        "ambiguity_status": ambiguity_status,
        "candidate_count": candidate_count,
        "candidate_columns": candidate_columns[:30],
        "example_column": candidate_columns[0] if candidate_columns else None,
        "issue": issue,
        **metadata,
    }


def _dimension_role_match(role_resolution: dict[str, Any]) -> dict[str, Any]:
    issues = list(role_resolution.get("issues") or [])
    prerequisite_matches = role_resolution.get("prerequisite_matches") or {}
    matched_columns: list[str] = []
    for values in prerequisite_matches.values():
        matched_columns.extend(str(value) for value in values)
    matched_columns.extend(
        str(value) for value in role_resolution.get("candidate_columns") or []
    )
    if "requires_semantic_or_package_role" in issues:
        fit_status = "semantic_or_package_gap"
        issue = "requires_semantic_or_package_role"
    elif issues:
        fit_status = "missing"
        issue = ",".join(issues)
    else:
        fit_status = "satisfied"
        issue = None
    match = _mechanical_role_match(
        kind="dimension",
        role=str(role_resolution["role"]),
        candidate_columns=list(dict.fromkeys(matched_columns)),
        required=bool(role_resolution.get("required", True)),
        issue=issue if fit_status != "satisfied" else None,
        resolution_type=role_resolution.get("resolution_type"),
        required_profile_roles=role_resolution.get("required_profile_roles") or [],
        missing_profile_roles=role_resolution.get("missing_profile_roles") or [],
    )
    match["fit_status"] = fit_status
    if fit_status == "semantic_or_package_gap":
        match["ambiguity_status"] = "not_applicable"
    return match


def check_profile_compatibility(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    *,
    manifest_source: str = "in_memory",
    profile_source: str = "in_memory",
) -> dict[str, Any]:
    """Return all-capability mechanical compatibility evidence."""

    results = [
        _capability_profile_match(capability, profile)
        for capability in manifest["capabilities"].values()
    ]
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {
        "schema_version": "0.2",
        "manifest": manifest_source,
        "dataset_profile": profile_source,
        "dataset_id": profile["dataset_id"],
        "dataset_profile_schema_version": profile.get("schema_version"),
        "counts": dict(sorted(counts.items())),
        "selector_boundary": (
            "This audit only checks mechanical compatibility between the dataset "
            "profile and chart manifest. It does not decide whether the analysis "
            "makes business sense."
        ),
        "results": results,
    }


def check_capability_compatibility(
    capability_id: str,
    profile: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return mechanical compatibility for one known capability."""

    resolved_manifest = manifest or _load_json(DEFAULT_MANIFEST)
    capability = (resolved_manifest.get("capabilities") or {}).get(capability_id)
    if not isinstance(capability, dict):
        raise KeyError(f"Unknown capability: {capability_id}")
    return _capability_profile_match(capability, profile)


def audit_manifest_against_dataset_profile(
    manifest_path: Path, profile_path: Path
) -> dict[str, Any]:
    """Load persisted inputs and return all-capability compatibility evidence."""

    return check_profile_compatibility(
        _load_json(manifest_path),
        _load_json(profile_path),
        manifest_source=str(manifest_path),
        profile_source=str(profile_path),
    )


def _write_markdown(path: Path, audit: dict[str, Any]) -> None:
    lines = [
        f"# Dataset Profile Chart Compatibility: {audit['dataset_id']}",
        "",
        "## Counts",
        "",
    ]
    for status, count in audit["counts"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(
        ["", "## Boundary", "", audit["selector_boundary"], "", "## Results", ""]
    )
    for result in audit["results"]:
        lines.append(
            f"- `{result['capability_id']}`: `{result['status']}`"
            f" / `{result['selection_emphasis']}`"
        )
        if result["issues"]:
            lines.append(f"  - Issues: `{', '.join(result['issues'])}`")
        for match in result["source_metric_matches"]:
            candidates = ", ".join(
                f"`{column}`" for column in match["candidate_columns"][:8]
            )
            lines.append(
                f"  - Metric `{match['role']}` candidates: {candidates or '`none`'}"
            )
        if result["period_candidates"]:
            periods = ", ".join(
                f"`{column}`" for column in result["period_candidates"][:4]
            )
            lines.append(f"  - Period candidates: {periods}")
        period_scope = result.get("period_scope") or {}
        if period_scope.get("status") not in {None, "not_applicable"}:
            lines.append(
                "  - Period scope: "
                f"`{period_scope.get('status')}`"
                f" / role `{period_scope.get('role')}`"
                f" / required `{period_scope.get('scope_required_for_render')}`"
            )
            if period_scope.get("pre_render_warning"):
                lines.append(f"    - {period_scope['pre_render_warning']}")
        for match in result.get("mechanical_role_matches") or []:
            candidates = ", ".join(
                f"`{column}`" for column in match.get("candidate_columns", [])[:5]
            )
            lines.append(
                "  - Role "
                f"`{match['kind']}.{match['role']}`: "
                f"`{match['fit_status']}`"
                f" / `{match['ambiguity_status']}`"
                f" / candidates: {candidates or '`none`'}"
            )
        for rejected in result.get("rejected_column_evidence") or []:
            samples = ", ".join(
                f"`{sample['column']}` ({sample['reason']})"
                for sample in rejected.get("samples", [])[:5]
            )
            not_applicable = rejected.get("not_applicable_reason")
            suffix = (
                f" / `{not_applicable}`"
                if not_applicable
                else f" / samples: {samples or '`none`'}"
            )
            lines.append(
                "  - Rejected "
                f"`{rejected['kind']}.{rejected['role']}`: "
                f"`{rejected['rejected_count']}`"
                f"{suffix}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Write JSON and Markdown compatibility evidence."""

    parser = argparse.ArgumentParser(
        description="Audit chart manifest mechanical compatibility against a dataset profile."
    )
    parser.add_argument("dataset_profile", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    audit = audit_manifest_against_dataset_profile(args.manifest, args.dataset_profile)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown_output = output.with_suffix(".md")
    _write_markdown(markdown_output, audit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
