"""Exercise Reporting Engine contracts without making semantic chart choices.

The fixture binding is deterministic because this command verifies mechanically
observable contracts only: profile roles, compatibility, parameter targets, and
optional component execution. It must not be used to choose a chart for a report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_compatibility import check_profile_compatibility
from profile_dataset import profile_dataset
from render_capability import (
    ARTIFACT_MODE_DATA_ONLY,
    ARTIFACT_MODES,
    RenderRequest,
    build_render_recipe,
    render_capability,
)
from reporting_adapters import load_manifest, prepare_invocation_plan

__all__ = [
    "build_mechanical_acceptance",
    "build_mechanical_acceptance_summary",
    "build_role_bindings",
    "main",
]

FIXTURE_ROOT = SCRIPT_DIR.parent / "fixtures" / "mechanical_acceptance"
SUITE_DATASETS = [
    FIXTURE_ROOT / "universal_complete.csv",
    FIXTURE_ROOT / "variance_root_cause.csv",
    FIXTURE_ROOT / "funnel_stage.csv",
    FIXTURE_ROOT / "set_overlap.csv",
    FIXTURE_ROOT / "statement.csv",
]
SUITE_RECIPE_PATHS = {
    "statement.pnl_table": FIXTURE_ROOT / "statement_recipe.json",
    "attributes.attribute_bridge_table": FIXTURE_ROOT / "attribute_recipe.json",
    "attributes.attribute_bundle_comparison_table": (
        FIXTURE_ROOT / "attribute_recipe.json"
    ),
    "attributes.product_signal_evidence_table": (
        FIXTURE_ROOT / "attribute_recipe.json"
    ),
    "attributes.rank_weighted_visibility_table": (
        FIXTURE_ROOT / "attribute_recipe.json"
    ),
}
SUITE_DATASET_IDS_BY_FAMILY = {
    "attributes": "universal_complete",
    "distribution": "universal_complete",
    "funnel": "funnel_stage",
    "mix": "universal_complete",
    "period_comparison": "universal_complete",
    "scatter_bubble": "universal_complete",
    "set_overlap": "set_overlap",
    "statement": "statement",
    "variance": "variance_root_cause",
}
FAILURE_STATUSES = {
    "binding_gap",
    "execution_failed",
    "period_scope_gap",
    "recipe_failed",
    "render_output_gap",
}

SEMANTIC_OR_PACKAGE_ISSUES = {
    "requires_semantic_or_package_metric_source",
    "requires_semantic_or_package_role",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _deep_get(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return True


def _role_supplied_by_recipe(
    capability: dict[str, Any], role: str, recipe: dict[str, Any]
) -> bool:
    contract = capability.get("normalized_invocation_contract") or {}
    role_contracts = list(contract.get("required_role_contracts") or [])
    role_contracts.extend(contract.get("optional_role_contracts") or [])
    role_contract = next(
        (item for item in role_contracts if item.get("role") == role), None
    )
    if not isinstance(role_contract, dict):
        return False
    targets = [
        str(target.get("target") or "")
        for target in role_contract.get("parameter_targets") or []
        if target.get("target_type") in {"recipe_path", "artifact_contract_parameter"}
        and not target.get("scope_control")
    ]
    return bool(targets) and all(
        _has_value(_deep_get(recipe, target)) for target in targets
    )


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._") or "dataset"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolved_package_dir(recipe_path: Path, value: Any) -> Path | None:
    if not _has_value(value):
        return None
    package_dir = Path(str(value)).expanduser()
    if not package_dir.is_absolute():
        package_dir = recipe_path.parent / package_dir
    return package_dir.resolve()


def _candidate_columns(profile: dict[str, Any], role: str) -> list[str]:
    flattened = (profile.get("role_candidate_columns") or {}).get(role) or []
    if flattened:
        return [str(column) for column in flattened]
    values = (profile.get("role_candidates") or {}).get(role) or []
    columns: list[str] = []
    for value in values:
        if isinstance(value, dict) and value.get("column"):
            columns.append(str(value["column"]))
        elif isinstance(value, str):
            columns.append(value)
    return columns


def _physical_candidates(profile: dict[str, Any], candidates: list[str]) -> list[str]:
    columns = profile.get("columns") or {}
    return [candidate for candidate in candidates if candidate in columns]


def _compatibility_match_map(
    compatibility: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(match.get("kind") or ""), str(match.get("role") or "")): match
        for match in compatibility.get("mechanical_role_matches") or []
        if isinstance(match, dict)
    }


def _role_resolution_map(
    compatibility: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(resolution.get("role")): resolution
        for resolution in compatibility.get("role_resolutions") or []
        if isinstance(resolution, dict) and resolution.get("role")
    }


def _first_unused(candidates: list[str], used: set[str]) -> str | None:
    for candidate in candidates:
        if candidate not in used:
            used.add(candidate)
            return candidate
    return candidates[0] if candidates else None


def _period_binding(
    profile: dict[str, Any], capability: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    periods = [str(value) for value in (profile.get("roles") or {}).get("period", [])]
    if not periods:
        return None
    period = periods[0]
    column_profile = (profile.get("columns") or {}).get(period) or {}
    parseability = column_profile.get("period_parseability") or {}
    parsed_min = _date_value(
        parseability.get("parsed_min") or column_profile.get("min")
    )
    parsed_max = _date_value(
        parseability.get("parsed_max") or column_profile.get("max")
    )
    period_grain = str(
        parseability.get("inferred_grain")
        or column_profile.get("period_grain")
        or "month"
    )
    binding: dict[str, Any] = {
        "date_column": period,
        "period_column": period,
    }
    if parsed_max is not None:
        previous_year = (
            parsed_max.year - 1
            if parsed_min is None or parsed_min.year < parsed_max.year
            else parsed_max.year
        )
        bounded_start = date(previous_year, 1, 1)
        selected_period, filter_start, filter_end = _period_scope_values(
            column_profile,
            period_grain=period_grain,
            previous_year=previous_year,
            bounded_start=bounded_start,
            parsed_max=parsed_max,
        )
        binding.update(
            {
                "selected_period": selected_period,
                "period_type": "calendar",
                "period_grain": period_grain,
                "period_window": {
                    "current": {
                        "year": parsed_max.year,
                        "month_cutoff": parsed_max.month,
                    },
                    "previous": {
                        "year": previous_year,
                        "month_cutoff": parsed_max.month,
                    },
                },
                "filters": [
                    {
                        "column": period,
                        "gte": filter_start,
                        "lte": filter_end,
                        "display_in_title": False,
                    }
                ],
            }
        )
        comparison_periods = _comparison_period_values(
            column_profile,
            current_period=selected_period,
            parsed_max=parsed_max,
            previous_year=previous_year,
            period_grain=period_grain,
        )
        if comparison_periods is not None:
            previous_period, current_period = comparison_periods
            binding.update(
                {
                    "current_period_label": str(current_period),
                    "previous_period_label": str(previous_period),
                    "comparison_period": str(current_period),
                    "baseline_period": str(previous_period),
                }
            )
            if bool(
                ((capability or {}).get("period_semantics") or {}).get(
                    "requires_comparison_pair", False
                )
            ):
                binding["period_selection"] = "explicit_comparison_periods"
        period_semantics = (capability or {}).get("period_semantics") or {}
        if (
            period_semantics.get("role") == "filter"
            and not period_semantics.get("requires_period_column", True)
            and (capability or {}).get("family")
            in {"distribution", "mix", "scatter_bubble"}
        ):
            binding.update(
                {
                    "period_type": "rolling",
                    "period_grain": "month",
                    "period_comparison_mode": "rolling_period",
                    "rolling_window_months": 12,
                }
            )
    return binding


def _comparison_period_values(
    column_profile: dict[str, Any],
    *,
    current_period: Any,
    parsed_max: date,
    previous_year: int,
    period_grain: str,
) -> tuple[Any, Any] | None:
    """Return an observed baseline/current pair from profiled period values."""

    ordered_values = list(column_profile.get("ordered_values") or [])
    if not ordered_values:
        return None
    current = next(
        (value for value in ordered_values if str(value) == str(current_period)),
        ordered_values[-1],
    )
    if period_grain == "year":
        target_previous = (
            str(previous_year) if isinstance(current, str) else previous_year
        )
    else:
        try:
            target_previous = parsed_max.replace(year=previous_year).isoformat()
        except ValueError:
            target_previous = parsed_max.replace(year=previous_year, day=28).isoformat()
    previous = next(
        (value for value in ordered_values if str(value) == str(target_previous)),
        None,
    )
    if previous is None:
        current_index = next(
            (
                index
                for index, value in enumerate(ordered_values)
                if str(value) == str(current)
            ),
            len(ordered_values) - 1,
        )
        if current_index <= 0:
            return None
        previous = ordered_values[current_index - 1]
    if str(previous) == str(current):
        return None
    return previous, current


def _period_scope_values(
    column_profile: dict[str, Any],
    *,
    period_grain: str,
    previous_year: int,
    bounded_start: date,
    parsed_max: date,
) -> tuple[Any, Any, Any]:
    """Preserve raw annual period types while using ISO bounds for date columns."""

    raw_min = column_profile.get("min")
    raw_max = column_profile.get("max")
    physical_type = str(column_profile.get("physical_type") or "")
    numeric_period = physical_type.startswith(("Int", "UInt", "Float"))
    string_year_period = (
        period_grain == "year"
        and isinstance(raw_max, str)
        and raw_max.strip().isdigit()
        and len(raw_max.strip()) == 4
    )
    if period_grain == "year" and (numeric_period or string_year_period):
        previous_value: Any = previous_year
        if string_year_period:
            previous_value = str(previous_year)
        lower = (
            raw_min
            if raw_min is not None and raw_min > previous_value
            else previous_value
        )
        return raw_max, lower, raw_max
    return parsed_max.isoformat(), bounded_start.isoformat(), parsed_max.isoformat()


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _metric_binding(
    profile: dict[str, Any],
    match: dict[str, Any] | None,
    used: set[str],
) -> str | None:
    candidates = [str(value) for value in (match or {}).get("candidate_columns") or []]
    candidates = _physical_candidates(profile, candidates)
    if not candidates:
        candidates = [
            str(value) for value in (profile.get("roles") or {}).get("metric", [])
        ]
    return _first_unused(candidates, used)


def _prerequisite_columns(
    profile: dict[str, Any], resolution: dict[str, Any], role: str
) -> list[str]:
    prerequisites = resolution.get("prerequisite_matches") or {}
    role_values = prerequisites.get(role) or []
    values = [str(column) for column in role_values]
    if values:
        return list(dict.fromkeys(values))
    return _candidate_columns(profile, role)


def _dimension_binding(
    profile: dict[str, Any],
    role: str,
    match: dict[str, Any] | None,
    resolution: dict[str, Any] | None,
    used: set[str],
) -> Any:
    resolved = resolution or {}
    resolution_type = str(resolved.get("resolution_type") or "direct_dimension")
    if resolution_type == "semantic_or_package_role":
        return None
    if resolution_type in {"direct_dimension", "direct_rank_or_lane", "schema_role"}:
        candidates = [
            str(value) for value in (match or {}).get("candidate_columns") or []
        ]
        if not candidates:
            candidates = _candidate_columns(profile, role)
        return _first_unused(_physical_candidates(profile, candidates), used)

    prerequisites = resolved.get("prerequisite_matches") or {}
    period = next(iter(prerequisites.get("period") or []), None)
    entity = next(iter(prerequisites.get("entity_key") or []), None)
    if resolution_type == "derived_from_period_pair":
        return period or _period_binding(profile)
    if resolution_type == "derived_from_entity_period":
        if period is None or entity is None:
            return None
        binding: dict[str, Any] = {
            "date_column": str(period),
            "period_column": str(period),
            "dimensions": [str(entity)],
            "period_selection": "explicit_comparison_periods",
        }
        if role == "stable_population_flag":
            binding["like_for_like"] = {"source_dimension": str(entity)}
        elif role in {"first_active_cohort", "lost_or_last_active_cohort"}:
            kind = "since" if role == "first_active_cohort" else "lost"
            binding["derived_dimensions"] = [
                {"kind": kind, "source_dimension": str(entity)}
            ]
        return binding
    if resolution_type == "derived_set_membership":
        item = next(iter(prerequisites.get("set_item") or []), None)
        set_column = next(iter(prerequisites.get("set_dimension") or []), None)
        if item is None or set_column is None:
            return None
        used.update({str(item), str(set_column)})
        return {"item_column": str(item), "set_column": str(set_column)}
    if resolution_type == "derived_root_cause_sequence":
        dimensions = _prerequisite_columns(profile, resolved, "direct_dimension")
        relationships = resolved.get("multidimensional_relationship_evidence") or []
        selected = dimensions[:3]
        selected_set = set(selected)
        selected_has_supported_pair = any(
            relationship.get("left_column") in selected_set
            and relationship.get("right_column") in selected_set
            for relationship in relationships
        )
        if not selected_has_supported_pair and relationships:
            relationship = relationships[0]
            pair = {
                str(value)
                for value in (
                    relationship.get("left_column"),
                    relationship.get("right_column"),
                )
                if value
            }
            selected = [dimension for dimension in dimensions if dimension in pair]
            selected.extend(
                dimension for dimension in dimensions if dimension not in selected
            )
        return {"dimensions": selected[:3]} if selected else None
    if resolution_type == "structural_row_selection":
        return {
            "root_cause_bridge_alternative_result": 3,
            "root_cause_bridge_drilldown_rows": [1],
        }
    if resolution_type in {
        "derived_period_or_scenario_pair",
        "structural_variance_step",
    }:
        return period or _period_binding(profile)
    candidates = [str(value) for value in (match or {}).get("candidate_columns") or []]
    return candidates[0] if candidates else None


def build_role_bindings(
    capability: dict[str, Any],
    profile: dict[str, Any],
    compatibility: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Build fixture-only bindings that exercise every required parameter target."""

    contract = capability.get("normalized_invocation_contract") or {}
    matches = _compatibility_match_map(compatibility)
    resolutions = _role_resolution_map(compatibility)
    bindings: dict[str, Any] = {}
    missing: list[str] = []
    used_metrics: set[str] = set()
    used_dimensions: set[str] = set()
    role_contracts = list(contract.get("required_role_contracts") or [])
    role_contracts.extend(contract.get("optional_role_contracts") or [])
    for role_contract in role_contracts:
        kind = str(role_contract.get("kind") or "")
        role = str(role_contract.get("role") or "")
        required = bool(role_contract.get("required", True))
        depends_on_role = role_contract.get("depends_on_role")
        if depends_on_role:
            if str(depends_on_role) not in bindings and required:
                missing.append(role)
            continue
        match = matches.get((kind, role))
        if kind == "period":
            binding = _period_binding(profile, capability)
        elif kind == "metric":
            binding = _metric_binding(profile, match, used_metrics)
        elif kind == "dimension":
            binding = _dimension_binding(
                profile,
                role,
                match,
                resolutions.get(role),
                used_dimensions,
            )
        elif kind == "identifier":
            binding = _first_unused(
                [
                    str(value)
                    for value in (profile.get("roles") or {}).get("identifier", [])
                ],
                used_dimensions,
            )
        else:
            binding = None
        if binding is None:
            if required:
                missing.append(role)
        else:
            bindings[role] = binding
    _apply_dimension_pair_contract(capability, profile, bindings)
    return bindings, missing


def _apply_dimension_pair_contract(
    capability: dict[str, Any],
    profile: dict[str, Any],
    bindings: dict[str, Any],
) -> None:
    """Bind a profiled non-redundant pair when a chart contract requires one."""

    contract = capability.get("dimension_contract") or {}
    if not contract.get("requires_non_bijective_dimension_pair"):
        return
    roles = [str(role) for role in contract.get("required_roles") or []]
    if len(roles) < 2:
        return
    relationships = [
        relationship
        for relationship in profile.get("dimension_relationships") or []
        if relationship.get("supports_multidimensional_path")
    ]
    if not relationships:
        return
    current = {str(bindings.get(role)) for role in roles[:2] if bindings.get(role)}
    if len(current) == 2 and any(
        {
            str(relationship.get("left_column")),
            str(relationship.get("right_column")),
        }
        == current
        for relationship in relationships
    ):
        return
    relationship = relationships[0]
    bindings[roles[0]] = str(relationship["left_column"])
    bindings[roles[1]] = str(relationship["right_column"])


def _dataset_score(
    compatibility: dict[str, Any],
) -> tuple[int, int, int, int, int]:
    status_rank = 0 if compatibility.get("status") == "mechanically_compatible" else 1
    missing_count = len(compatibility.get("unmatched_required_roles") or [])
    observation_rows = int(
        (compatibility.get("observation_evidence") or {}).get(
            "available_observation_rows"
        )
        or 0
    )
    period_values = int(
        (compatibility.get("period_scope") or {}).get(
            "available_distinct_period_values"
        )
        or 0
    )
    ambiguity_count = len(compatibility.get("ambiguous_required_roles") or [])
    return (
        status_rank,
        missing_count,
        -observation_rows,
        -period_values,
        ambiguity_count,
    )


def _package_gap(compatibility: dict[str, Any]) -> bool:
    issues = set(compatibility.get("issues") or [])
    return bool(issues) and issues.issubset(SEMANTIC_OR_PACKAGE_ISSUES)


def _acceptance_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Reporting Engine Mechanical Acceptance",
        "",
        str(payload["boundary"]),
        "",
        "## Counts",
        "",
    ]
    for status, count in payload["counts"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Capabilities", ""])
    for record in payload["records"]:
        lines.append(
            f"- `{record['capability_id']}`: `{record['status']}`"
            f" / dataset `{record.get('dataset_id') or 'none'}`"
        )
        if record.get("issues"):
            lines.append(f"  - Issues: `{', '.join(record['issues'])}`")
        if record.get("missing_bindings"):
            lines.append(
                f"  - Missing bindings: `{', '.join(record['missing_bindings'])}`"
            )
        if record.get("error"):
            lines.append(f"  - Error: {record['error']}")
    return "\n".join(lines) + "\n"


def build_mechanical_acceptance(
    dataset_paths: list[Path],
    *,
    output_dir: Path,
    execute: bool = False,
    artifact_mode: str = ARTIFACT_MODE_DATA_ONLY,
    capability_ids: set[str] | None = None,
    recipe_paths: dict[str, Path] | None = None,
    dataset_ids_by_capability: dict[str, str] | None = None,
    dataset_ids_by_family: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Profile datasets and exercise all manifest capabilities mechanically."""

    if not dataset_paths:
        raise ValueError("At least one dataset is required.")
    resolved_root = root or SCRIPT_DIR.parent
    if resolved_root == output_dir or resolved_root in output_dir.parents:
        raise ValueError(
            "Acceptance output must be outside the Reporting Engine component."
        )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(
            "Acceptance output directory must be empty so stale artifacts cannot "
            "affect render proof."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(resolved_root)
    resolved_recipe_paths = dict(recipe_paths or {})
    resolved_dataset_ids = dict(dataset_ids_by_capability or {})
    resolved_family_dataset_ids = dict(dataset_ids_by_family or {})
    selected_capabilities = set(capability_ids or manifest["capabilities"])
    unknown_capabilities = selected_capabilities - set(manifest["capabilities"])
    if unknown_capabilities:
        raise KeyError(
            "Unknown capabilities: " + ", ".join(sorted(unknown_capabilities))
        )
    datasets: list[dict[str, Any]] = []
    for index, dataset_path in enumerate(dataset_paths, start=1):
        dataset_id = _safe_name(dataset_path.stem or f"dataset_{index}")
        profile = profile_dataset(dataset_path, dataset_id=dataset_id)
        profile_path = output_dir / "profiles" / f"{dataset_id}.json"
        _write_json(profile_path, profile)
        compatibility = check_profile_compatibility(
            manifest,
            profile,
            manifest_source=str(resolved_root / "catalog" / "selection_manifest.json"),
            profile_source=str(profile_path),
        )
        compatibility_path = output_dir / "compatibility" / f"{dataset_id}.json"
        _write_json(compatibility_path, compatibility)
        datasets.append(
            {
                "dataset_id": dataset_id,
                "path": dataset_path,
                "profile": profile,
                "profile_path": profile_path,
                "compatibility": {
                    str(result["capability_id"]): result
                    for result in compatibility["results"]
                },
                "compatibility_path": compatibility_path,
            }
        )

    dataset_summary = [
        {
            "dataset_id": dataset["dataset_id"],
            "path": str(dataset["path"]),
            "profile": str(dataset["profile_path"]),
            "compatibility": str(dataset["compatibility_path"]),
        }
        for dataset in datasets
    ]
    datasets_by_id = {str(dataset["dataset_id"]): dataset for dataset in datasets}
    unknown_dataset_ids = (
        set(resolved_dataset_ids.values()) | set(resolved_family_dataset_ids.values())
    ) - set(datasets_by_id)
    if unknown_dataset_ids:
        raise KeyError(
            "Unknown acceptance dataset IDs: " + ", ".join(sorted(unknown_dataset_ids))
        )
    records: list[dict[str, Any]] = []

    def write_checkpoint() -> None:
        _write_json(
            output_dir / "mechanical_acceptance.partial.json",
            {
                "schema_version": "0.1",
                "execute": execute,
                "artifact_mode": artifact_mode,
                "selected_capabilities": sorted(selected_capabilities),
                "datasets": dataset_summary,
                "counts": dict(
                    sorted(Counter(record["status"] for record in records).items())
                ),
                "records": records,
            },
        )

    for capability_id, capability in sorted(manifest["capabilities"].items()):
        if capability_id not in selected_capabilities:
            continue
        ranked = sorted(
            datasets,
            key=lambda dataset: _dataset_score(dataset["compatibility"][capability_id]),
        )
        preferred_dataset_id = resolved_dataset_ids.get(capability_id)
        if preferred_dataset_id is None:
            preferred_dataset_id = resolved_family_dataset_ids.get(
                str(capability.get("family") or "")
            )
        dataset = (
            datasets_by_id[preferred_dataset_id]
            if preferred_dataset_id is not None
            else ranked[0]
        )
        compatibility = dataset["compatibility"][capability_id]
        explicit_recipe_path = resolved_recipe_paths.get(capability_id)
        if explicit_recipe_path is not None:
            explicit_recipe_path = explicit_recipe_path.expanduser().resolve()
        explicit_recipe = (
            _load_json(explicit_recipe_path) if explicit_recipe_path is not None else {}
        )
        record: dict[str, Any] = {
            "capability_id": capability_id,
            "dataset_id": dataset["dataset_id"],
            "dataset_path": str(dataset["path"]),
            "compatibility_status": compatibility.get("status"),
            "issues": compatibility.get("issues") or [],
            "period_scope": compatibility.get("period_scope") or {},
            "explicit_recipe_path": (
                str(explicit_recipe_path) if explicit_recipe_path is not None else None
            ),
        }
        package_gap_with_recipe = bool(
            explicit_recipe_path is not None and _package_gap(compatibility)
        )
        if (
            compatibility.get("status") != "mechanically_compatible"
            and not package_gap_with_recipe
        ):
            record["status"] = (
                "package_contract_gap"
                if _package_gap(compatibility)
                else "correct_mechanical_rejection"
            )
            records.append(record)
            write_checkpoint()
            continue

        bindings, missing_bindings = build_role_bindings(
            capability,
            dataset["profile"],
            compatibility,
        )
        package_dir = (
            _resolved_package_dir(
                explicit_recipe_path,
                explicit_recipe.get("package_dir"),
            )
            if explicit_recipe_path is not None
            else None
        )
        if package_dir is not None:
            bindings["package_dir"] = str(package_dir)
        recipe_supplied_roles = [
            role
            for role in missing_bindings
            if _role_supplied_by_recipe(capability, role, explicit_recipe)
        ]
        missing_bindings = [
            role for role in missing_bindings if role not in recipe_supplied_roles
        ]
        record["role_bindings"] = bindings
        record["missing_bindings"] = missing_bindings
        record["recipe_supplied_roles"] = recipe_supplied_roles
        record["invocation_plan"] = prepare_invocation_plan(
            capability_id,
            dataset_profile=dataset["profile"],
            root=resolved_root,
        )
        capability_output = output_dir / "capabilities" / capability_id
        request = RenderRequest(
            capability_id=capability_id,
            input_file=dataset["path"],
            output_dir=capability_output,
            recipe_path=explicit_recipe_path,
            dataset_profile=dataset["profile"],
            role_bindings=bindings,
            currency="EUR",
            artifact_mode=artifact_mode,
        )
        try:
            recipe_path, recipe_audit = build_render_recipe(request, root=resolved_root)
            record["recipe_path"] = str(recipe_path) if recipe_path else None
            record["recipe_audit"] = recipe_audit
            period_scope_status = str(
                (recipe_audit.get("period_scope") or {}).get("status") or ""
            )
            if period_scope_status in {
                "missing_required_comparison_pair",
                "unscoped_filter_defaults_to_all_available_data",
            }:
                record["status"] = "period_scope_gap"
            elif missing_bindings:
                record["status"] = "binding_gap"
            elif execute:
                render_manifest = render_capability(request, root=resolved_root)
                render_proof = render_manifest.get("render_proof") or {}
                record["render_proof"] = render_proof
                record["status"] = (
                    "render_output_gap"
                    if render_proof.get("status")
                    in {
                        "missing_expected_render",
                        "unexpected_rendered_artifacts",
                    }
                    else "component_executed"
                )
                record["render_manifest"] = str(
                    capability_output / "render_manifest.json"
                )
                record["artifacts"] = render_manifest.get("artifacts") or []
            else:
                record["status"] = "recipe_proven"
        except (
            ImportError,
            IndexError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            record["status"] = "execution_failed" if execute else "recipe_failed"
            record["error"] = str(error)
        records.append(record)
        write_checkpoint()

    counts = dict(sorted(Counter(record["status"] for record in records).items()))
    payload = {
        "schema_version": "0.1",
        "boundary": (
            "Mechanical acceptance only. Dataset selection and fixture bindings "
            "exercise explicit contracts and do not endorse a business analysis."
        ),
        "execute": execute,
        "artifact_mode": artifact_mode,
        "selected_capabilities": sorted(selected_capabilities),
        "datasets": dataset_summary,
        "counts": counts,
        "records": records,
    }
    _write_json(output_dir / "mechanical_acceptance.json", payload)
    (output_dir / "mechanical_acceptance.md").write_text(
        _acceptance_markdown(payload), encoding="utf-8"
    )
    return payload


def build_mechanical_acceptance_summary(
    payload: dict[str, Any],
    *,
    manifest_path: Path,
) -> dict[str, Any]:
    """Return compact, path-free evidence for a completed acceptance run."""

    dataset_evidence = []
    for dataset in payload.get("datasets") or []:
        dataset_path = Path(str(dataset["path"]))
        dataset_evidence.append(
            {
                "dataset_id": dataset["dataset_id"],
                "file_name": dataset_path.name,
                "sha256": _sha256_file(dataset_path),
            }
        )
    recipe_paths = sorted(
        {
            Path(str(record["explicit_recipe_path"]))
            for record in payload.get("records") or []
            if record.get("explicit_recipe_path")
        },
        key=lambda path: str(path),
    )
    recipe_evidence = [
        {
            "file_name": recipe_path.name,
            "sha256": _sha256_file(recipe_path),
        }
        for recipe_path in recipe_paths
    ]
    records = []
    for record in payload.get("records") or []:
        render_proof = record.get("render_proof") or {}
        records.append(
            {
                "capability_id": record["capability_id"],
                "dataset_id": record.get("dataset_id"),
                "compatibility_status": record.get("compatibility_status"),
                "acceptance_status": record.get("status"),
                "bound_roles": sorted((record.get("role_bindings") or {}).keys()),
                "missing_bindings": record.get("missing_bindings") or [],
                "period_scope_status": (
                    (record.get("recipe_audit") or {}).get("period_scope") or {}
                ).get("status"),
                "render_proof_status": render_proof.get("status"),
                "expected_artifact_stems": render_proof.get("expected_chart_tokens")
                or [],
                "rendered_artifacts": render_proof.get("rendered_artifacts") or [],
            }
        )
    selected_count = len(payload.get("selected_capabilities") or [])
    component_executed = int((payload.get("counts") or {}).get("component_executed", 0))
    return {
        "schema_version": "0.1",
        "result": (
            "pass"
            if payload.get("execute")
            and component_executed == selected_count
            and selected_count > 0
            else "incomplete"
        ),
        "boundary": payload.get("boundary"),
        "manifest": {
            "file_name": manifest_path.name,
            "sha256": _sha256_file(manifest_path),
        },
        "fixture_datasets": dataset_evidence,
        "fixture_recipes": recipe_evidence,
        "artifact_mode": payload.get("artifact_mode"),
        "execute": payload.get("execute"),
        "selected_capability_count": selected_count,
        "counts": payload.get("counts") or {},
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the packaged mechanical acceptance workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, nargs="*")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--suite",
        action="store_true",
        help="Use the packaged synthetic fixtures and family dataset bindings.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Write compact path-free acceptance evidence to this JSON file.",
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Limit the run to one capability; repeat to select several.",
    )
    parser.add_argument(
        "--artifact-mode",
        choices=sorted(ARTIFACT_MODES),
        default=ARTIFACT_MODE_DATA_ONLY,
    )
    parser.add_argument(
        "--recipe",
        action="append",
        default=[],
        metavar="CAPABILITY=PATH",
        help="Supply an explicit invocation recipe for one capability.",
    )
    parser.add_argument(
        "--dataset-for",
        action="append",
        default=[],
        metavar="CAPABILITY=DATASET_ID",
        help="Pin one capability to a profiled acceptance dataset.",
    )
    parser.add_argument(
        "--dataset-for-family",
        action="append",
        default=[],
        metavar="FAMILY=DATASET_ID",
        help="Pin one chart family to a profiled acceptance dataset.",
    )
    args = parser.parse_args(argv)
    recipe_paths: dict[str, Path] = {}
    for value in args.recipe:
        capability_id, separator, path_value = value.partition("=")
        if not separator or not capability_id or not path_value:
            parser.error("--recipe must use CAPABILITY=PATH")
        recipe_paths[capability_id] = Path(path_value)
    dataset_ids_by_capability: dict[str, str] = {}
    for value in args.dataset_for:
        capability_id, separator, dataset_id = value.partition("=")
        if not separator or not capability_id or not dataset_id:
            parser.error("--dataset-for must use CAPABILITY=DATASET_ID")
        dataset_ids_by_capability[capability_id] = dataset_id
    dataset_ids_by_family: dict[str, str] = {}
    for value in args.dataset_for_family:
        family, separator, dataset_id = value.partition("=")
        if not separator or not family or not dataset_id:
            parser.error("--dataset-for-family must use FAMILY=DATASET_ID")
        dataset_ids_by_family[family] = dataset_id
    dataset_paths = list(args.dataset)
    if args.suite:
        if dataset_paths:
            parser.error("Do not pass dataset paths together with --suite")
        dataset_paths = list(SUITE_DATASETS)
        suite_recipe_paths = dict(SUITE_RECIPE_PATHS)
        suite_recipe_paths.update(recipe_paths)
        recipe_paths = suite_recipe_paths
        suite_family_bindings = dict(SUITE_DATASET_IDS_BY_FAMILY)
        suite_family_bindings.update(dataset_ids_by_family)
        dataset_ids_by_family = suite_family_bindings
    elif not dataset_paths:
        parser.error("Pass at least one dataset or use --suite")
    payload = build_mechanical_acceptance(
        dataset_paths,
        output_dir=args.output_dir,
        execute=args.execute,
        artifact_mode=args.artifact_mode,
        capability_ids=set(args.capability) or None,
        recipe_paths=recipe_paths,
        dataset_ids_by_capability=dataset_ids_by_capability,
        dataset_ids_by_family=dataset_ids_by_family,
    )
    if args.summary_output is not None:
        summary = build_mechanical_acceptance_summary(
            payload,
            manifest_path=SCRIPT_DIR.parent / "catalog" / "selection_manifest.json",
        )
        _write_json(args.summary_output, summary)
    return 1 if FAILURE_STATUSES.intersection(payload["counts"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
