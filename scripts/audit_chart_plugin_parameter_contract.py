from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "CAPABILITY_ROLE_PARAMETER_CANDIDATES",
    "ROLE_PARAMETER_CANDIDATES",
    "build_normalized_invocation_contract",
    "build_role_registry",
    "audit_chart_plugin_parameter_contract",
    "main",
]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION_MANIFEST = (
    REPO_ROOT / "plugins" / "reporting-engine" / "catalog" / "selection_manifest.json"
)
ADAPTER_REGISTRY_PATH = (
    REPO_ROOT / "plugins" / "reporting-engine" / "catalog" / "adapter_registry.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "plugin_parameter_contract_audit.json"
)
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_JSON.with_suffix(".md")
GALLERY_DIR = REPO_ROOT / "static" / "shared" / "png-gallery"


# This audit is deterministic because it verifies an exact mechanical contract:
# manifest role names must be supported by explicit recipe, catalog, or artifact
# contract parameter names. Semantic validity remains outside this script.
ROLE_PARAMETER_CANDIDATES: dict[str, list[dict[str, Any]]] = {
    "period_axis": [
        {"kind": "explicit", "paths": ["mappings.date_column"]},
        {"kind": "explicit", "paths": ["mappings.period_column"]},
        {"kind": "explicit", "paths": ["options.period_window"]},
        {"kind": "explicit", "paths": ["periods"]},
    ],
    "period_filter": [
        {"kind": "explicit", "paths": ["mappings.period_column"]},
        {"kind": "explicit", "paths": ["mappings.date_column"]},
        {"kind": "explicit", "paths": ["mappings.baseline_period"]},
        {"kind": "explicit", "paths": ["mappings.comparison_period"]},
        {"kind": "explicit", "paths": ["options.selected_period"]},
        {"kind": "explicit", "paths": ["options.selected_periods"]},
        {"kind": "explicit", "paths": ["options.period_window"]},
        {"kind": "explicit", "paths": ["periods"]},
    ],
    "comparison_metric": [
        {"kind": "explicit", "paths": ["mappings.amount_column"]},
        {"kind": "explicit", "paths": ["mappings.metric_column"]},
        {"kind": "contract", "parameters": ["metric"]},
    ],
    "primary_metric": [
        {"kind": "explicit", "paths": ["mappings.amount_column"]},
        {"kind": "explicit", "paths": ["mappings.metric_column"]},
        {"kind": "explicit", "paths": ["mappings.source_amount_column"]},
        {"kind": "contract", "parameters": ["metric"]},
    ],
    "primary_additive_metric": [
        {"kind": "explicit", "paths": ["mappings.amount_column"]},
        {"kind": "explicit", "paths": ["mappings.source_amount_column"]},
        {"kind": "contract", "parameters": ["metric"]},
    ],
    "distribution_metric": [
        {"kind": "explicit", "paths": ["mappings.metric_column"]},
        {"kind": "contract", "parameters": ["metric"]},
    ],
    "variance_metric": [
        {"kind": "explicit", "paths": ["mappings.amount_column"]},
        {"kind": "contract", "parameters": ["metric"]},
    ],
    "value_metric": [{"kind": "explicit", "paths": ["mappings.amount_column"]}],
    "area_metric": [{"kind": "explicit", "paths": ["mappings.amount_column"]}],
    "volume_metric": [
        {"kind": "explicit", "paths": ["mappings.units_column"]},
        {"kind": "explicit", "paths": ["mappings.width_metric_column"]},
    ],
    "price_or_rate_metric": [
        {"kind": "explicit", "paths": ["mappings.price_column"]},
        {"kind": "explicit", "paths": ["mappings.rate_column"]},
        {"kind": "explicit", "paths": ["mappings.price_or_rate_metric_column"]},
        {
            "kind": "compound",
            "paths": ["mappings.amount_column", "mappings.units_column"],
        },
    ],
    "width_metric": [
        {"kind": "explicit", "paths": ["mappings.width_metric_column"]},
        {"kind": "explicit", "paths": ["mappings.units_column"]},
    ],
    "height_metric": [
        {
            "kind": "compound",
            "paths": ["mappings.amount_column", "mappings.width_metric_column"],
        }
    ],
    "related_marker_metric": [
        {"kind": "explicit", "paths": ["mappings.related_marker_metric_column"]},
        {"kind": "explicit", "paths": ["mappings.margin_percent_column"]},
        {"kind": "explicit", "paths": ["mappings.margin_column"]},
        {
            "kind": "compound",
            "paths": ["mappings.amount_column", "options.period_selection"],
        },
        {"kind": "contract", "parameters": ["related_marker_metric"]},
    ],
    "x_metric": [{"kind": "explicit", "paths": ["mappings.x_metric_column"]}],
    "y_metric": [{"kind": "explicit", "paths": ["mappings.y_metric_column"]}],
    "size_metric": [
        {"kind": "explicit", "paths": ["mappings.bubble_size_metric_column"]}
    ],
    "stage_start_count": [
        {"kind": "explicit", "paths": ["stage_table_mappings.start_count_column"]}
    ],
    "stage_pass_count": [
        {"kind": "explicit", "paths": ["stage_table_mappings.pass_count_column"]}
    ],
    "statement_value": [{"kind": "explicit", "paths": ["mappings.value_column"]}],
    "category": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "component_category": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "component_dimension": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "optional_component_dimension": [
        {"kind": "collection", "paths": ["mappings.dimensions"]}
    ],
    "width_category": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "height_category": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "stack_category": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "dimension_member": [
        {"kind": "explicit", "paths": ["options.total_by_dimension_bridge_dimension"]},
        {"kind": "collection", "paths": ["mappings.dimensions"]},
        {"kind": "contract", "parameters": ["dimension", "dimensions"]},
    ],
    "comparison_item": [{"kind": "collection", "paths": ["mappings.dimensions"]}],
    "point_dimension": [{"kind": "explicit", "paths": ["mappings.dot_dimension"]}],
    "optional_panel": [
        {"kind": "explicit", "paths": ["mappings.small_multiples_dimension"]},
        {"kind": "explicit", "paths": ["options.small_multiples_dimension"]},
        {"kind": "explicit", "paths": ["options.waterfall_small_multiples_dimension"]},
    ],
    "panel_dimension": [
        {"kind": "explicit", "paths": ["mappings.small_multiples_dimension"]},
        {"kind": "explicit", "paths": ["options.small_multiples_dimension"]},
        {"kind": "explicit", "paths": ["options.waterfall_small_multiples_dimension"]},
    ],
    "panel_or_segment": [
        {"kind": "explicit", "paths": ["mappings.small_multiples_dimension"]},
        {"kind": "collection", "paths": ["mappings.dimensions"]},
    ],
    "parent_driver": [
        {
            "kind": "explicit",
            "paths": ["options.exploded_variance_bridge_parent_dimension"],
        }
    ],
    "child_driver": [
        {
            "kind": "explicit",
            "paths": ["options.exploded_variance_bridge_child_dimension"],
        }
    ],
    "component_root_cause_driver_sequence": [
        {"kind": "collection", "paths": ["mappings.dimensions"]}
    ],
    "root_cause_driver_sequence": [
        {"kind": "collection", "paths": ["mappings.dimensions"]},
    ],
    "optional_drilldown_selection": [
        {
            "kind": "compound",
            "paths": [
                "options.root_cause_bridge_alternative_result",
                "options.root_cause_bridge_drilldown_rows",
            ],
        }
    ],
    "set_membership_fields": [
        {"kind": "compound", "paths": ["mappings.item_column", "mappings.set_column"]}
    ],
    "two_or_three_set_membership_fields": [
        {"kind": "compound", "paths": ["mappings.item_column", "mappings.set_column"]}
    ],
    "ordered_stage": [
        {"kind": "explicit", "paths": ["stage_table_mappings.stage_column"]}
    ],
    "statement_line_item": [{"kind": "explicit", "paths": ["mappings.row_key_column"]}],
    "statement_scenario": [{"kind": "explicit", "paths": ["mappings.scenario_column"]}],
    "statement_structure": [
        {
            "kind": "compound",
            "paths": ["statement_rows", "periods", "scenarios_by_period"],
        }
    ],
    "product": [{"kind": "package_contract", "parameters": ["package_dir"]}],
    "signal_bundle": [{"kind": "package_contract", "parameters": ["package_dir"]}],
    "cohort_layer": [{"kind": "package_contract", "parameters": ["package_dir"]}],
    "attribute_bundle": [{"kind": "package_contract", "parameters": ["package_dir"]}],
    "rank_or_lane": [{"kind": "package_contract", "parameters": ["package_dir"]}],
    "stable_population_flag": [
        {
            "kind": "compound",
            "paths": [
                "mappings.period_column",
                "mappings.dimensions",
                "options.period_selection",
                "options.like_for_like",
            ],
        }
    ],
    "first_active_cohort": [
        {
            "kind": "compound",
            "paths": [
                "mappings.period_column",
                "mappings.dimensions",
                "options.period_selection",
                "options.derived_dimensions",
            ],
        }
    ],
    "lost_or_last_active_cohort": [
        {
            "kind": "compound",
            "paths": [
                "mappings.period_column",
                "mappings.dimensions",
                "options.period_selection",
                "options.derived_dimensions",
            ],
        }
    ],
    "comparison_series": [{"kind": "derived_from_period", "role": "period_axis"}],
    "comparison_window": [{"kind": "derived_from_period", "role": "period_filter"}],
    "bridge_component_period": [{"kind": "derived_from_period", "role": "period_axis"}],
    "variance_step": [{"kind": "derived_from_period", "role": "period_filter"}],
    "period_or_scenario_pair": [
        {"kind": "derived_from_period", "role": "period_filter"}
    ],
    "drilldown_selection": [
        {
            "kind": "compound",
            "paths": [
                "options.root_cause_bridge_alternative_result",
                "options.root_cause_bridge_drilldown_rows",
            ],
        },
        {
            "kind": "explicit",
            "paths": ["options.exploded_variance_bridge_max_drilldowns"],
        },
    ],
}


# These mappings are supported directly by component runtimes rather than
# inferred from gallery examples. Capability scope prevents a generic period
# role from being mapped to a parameter that another component does not accept.
CAPABILITY_ROLE_PARAMETER_CANDIDATES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "set_overlap.upset_small_multiples": {
        "panel_or_segment": [
            {
                "kind": "runtime_contract",
                "paths": ["options.small_multiples_dimension"],
                "verified_by": "plugins/set-overlap-analysis/scripts/set_overlap_core.py",
            }
        ],
    },
    "funnel.stage_table": {
        "stage_start_count": [
            {
                "kind": "runtime_contract",
                "paths": ["stage_table_mappings.start_count_column"],
                "verified_by": "plugins/funnel-analysis/scripts/funnel_core.py:compute_funnel_rows_from_stage_table",
            }
        ],
        "stage_pass_count": [
            {
                "kind": "runtime_contract",
                "paths": ["stage_table_mappings.pass_count_column"],
                "verified_by": "plugins/funnel-analysis/scripts/funnel_core.py:compute_funnel_rows_from_stage_table",
            }
        ],
        "ordered_stage": [
            {
                "kind": "runtime_contract",
                "paths": ["stage_table_mappings.stage_column"],
                "verified_by": "plugins/funnel-analysis/scripts/funnel_core.py:compute_funnel_rows_from_stage_table",
            }
        ],
    },
    "statement.pnl_table": {
        "period_axis": [
            {
                "kind": "runtime_contract",
                "paths": ["mappings.period_column"],
                "verified_by": "plugins/statement-analysis/scripts/statement_core.py:_read_values",
            }
        ],
        "statement_value": [
            {
                "kind": "runtime_contract",
                "paths": ["mappings.value_column"],
                "verified_by": "plugins/statement-analysis/scripts/statement_core.py:_read_values",
            }
        ],
        "statement_line_item": [
            {
                "kind": "runtime_contract",
                "paths": ["mappings.row_key_column"],
                "verified_by": "plugins/statement-analysis/scripts/statement_core.py:_read_values",
            }
        ],
        "statement_scenario": [
            {
                "kind": "runtime_contract",
                "paths": ["mappings.scenario_column"],
                "verified_by": "plugins/statement-analysis/scripts/statement_core.py:_read_values",
            }
        ],
        "statement_structure": [
            {
                "kind": "runtime_contract",
                "paths": ["statement_rows", "periods", "scenarios_by_period"],
                "verified_by": "plugins/statement-analysis/scripts/statement_core.py:_validate_recipe",
            }
        ],
    },
}

_MIX_PERIOD_AXIS_CAPABILITIES = (
    "mix.area",
    "mix.cohort_lost_stacked_column",
    "mix.cohort_since_stacked_column",
    "mix.column",
    "mix.column_overlay",
    "mix.like_for_like_column",
    "mix.like_for_like_stacked_column",
    "mix.multitier_bar",
    "mix.stacked_column",
    "mix.timeline",
)
for _capability_id in _MIX_PERIOD_AXIS_CAPABILITIES:
    CAPABILITY_ROLE_PARAMETER_CANDIDATES.setdefault(_capability_id, {})[
        "period_axis"
    ] = [
        {
            "kind": "runtime_contract",
            "paths": ["mappings.date_column", "mappings.period_column"],
            "verified_by": "plugins/mix-contribution-analysis/scripts/mix_core.py:prepare_canonical_frame",
        }
    ]

CAPABILITY_ROLE_PARAMETER_CANDIDATES.setdefault("mix.barmekko", {}).update(
    {
        "area_metric": [
            {
                "kind": "runtime_contract",
                "paths": ["mappings.amount_column"],
                "verified_by": "plugins/mix-contribution-analysis/scripts/mix_core.py:prepare_canonical_frame",
            }
        ],
        "width_metric": [
            {
                "kind": "runtime_contract",
                "paths": ["mappings.width_metric_column"],
                "verified_by": "plugins/mix-contribution-analysis/scripts/mix_core.py:prepare_canonical_frame",
            }
        ],
    }
)

for _capability_id, _role, _option_path in (
    ("mix.like_for_like_column", "stable_population_flag", "options.like_for_like"),
    (
        "mix.like_for_like_stacked_column",
        "stable_population_flag",
        "options.like_for_like",
    ),
    (
        "mix.cohort_since_stacked_column",
        "first_active_cohort",
        "options.derived_dimensions",
    ),
    (
        "mix.cohort_lost_stacked_column",
        "lost_or_last_active_cohort",
        "options.derived_dimensions",
    ),
):
    CAPABILITY_ROLE_PARAMETER_CANDIDATES.setdefault(_capability_id, {})[_role] = [
        {
            "kind": "runtime_contract",
            "paths": [
                "mappings.period_column",
                "mappings.dimensions",
                "options.period_selection",
                _option_path,
            ],
            "verified_by": "plugins/_shared/vendor/modules/chart_harness/period_derivations.py",
        }
    ]

for _capability_id in (
    "variance.exploded_variance_bridge",
    "variance.price_volume_mix",
    "variance.root_cause_component_bridge",
    "variance.root_cause_exploded_bridge",
    "variance.root_cause_total_bridge",
    "variance.scenario_bridge",
    "variance.total_by_dimension_bridge",
):
    CAPABILITY_ROLE_PARAMETER_CANDIDATES.setdefault(_capability_id, {})[
        "period_filter"
    ] = [
        {
            "kind": "runtime_contract",
            "paths": [
                "mappings.period_column",
                "mappings.baseline_period",
                "mappings.comparison_period",
            ],
            "verified_by": "plugins/variance-analysis/scripts/variance_core.py:validate_recipe",
        }
    ]

PROFILE_ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "period": {
        "description": "Dataset column that can order or filter observations by time or period.",
        "produced_by": "dataset_profile.roles.period",
    },
    "metric": {
        "description": "Dataset column or derived metric candidate usable as a numeric measure.",
        "produced_by": "dataset_profile.roles.metric and dataset_profile.metric_classes",
    },
    "dimension": {
        "description": "Dataset column usable for grouping, ranking, panels, or composition.",
        "produced_by": "dataset_profile.roles.dimension",
    },
    "identifier": {
        "description": "Dataset column that mechanically identifies entities such as products or customers.",
        "produced_by": "dataset_profile.roles.identifier",
    },
    "direct_dimension": {
        "description": "Categorical grouping candidate; not a semantic endorsement.",
        "produced_by": "dataset_profile.role_candidates.direct_dimension",
    },
    "entity_key": {
        "description": "Entity candidate for cohorts, like-for-like populations, or set membership derivation.",
        "produced_by": "dataset_profile.role_candidates.entity_key",
    },
    "ordered_stage": {
        "description": "Ordered funnel stage candidate.",
        "produced_by": "dataset_profile.role_candidates.ordered_stage",
    },
    "rank_or_lane": {
        "description": "Rank, lane, band, bucket, or tier candidate.",
        "produced_by": "dataset_profile.role_candidates.rank_or_lane",
    },
    "set_dimension": {
        "description": "Low-cardinality set/group candidate for overlap analysis.",
        "produced_by": "dataset_profile.role_candidates.set_dimension",
    },
    "set_item": {
        "description": "Item/entity candidate for set membership aggregation.",
        "produced_by": "dataset_profile.role_candidates.set_item",
    },
    "statement_line_item": {
        "description": "Financial statement line item candidate.",
        "produced_by": "dataset_profile.role_candidates.statement_line_item",
    },
    "statement_scenario": {
        "description": "Scenario column candidate for structured statement values.",
        "produced_by": "dataset_profile.role_candidates.statement_scenario",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_sidecar(href: str) -> Path:
    return (GALLERY_DIR / href).resolve()


def _display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return True


def _flatten_available_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if _has_value(child):
                paths.add(child_prefix)
            paths.update(_flatten_available_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        if prefix and value:
            paths.add(prefix)
        for index, child in enumerate(value):
            paths.update(_flatten_available_paths(child, f"{prefix}.{index}"))
    return paths


def _contract_parameters(contract: dict[str, Any]) -> set[str]:
    parameters: set[str] = set()
    for key in ("required_parameters", "optional_parameters"):
        values = contract.get(key)
        if isinstance(values, list):
            parameters.update(str(value) for value in values if isinstance(value, str))
    execution_contract = contract.get("execution_contract")
    if isinstance(execution_contract, dict):
        for key in ("required_parameters", "optional_parameters"):
            values = execution_contract.get(key)
            if isinstance(values, list):
                parameters.update(
                    str(value) for value in values if isinstance(value, str)
                )
    return parameters


@lru_cache(maxsize=1)
def _adapter_registry() -> dict[str, Any]:
    return _load_json(ADAPTER_REGISTRY_PATH)


def _runtime_recipe_contract(plugin_source: str) -> dict[str, Any]:
    adapters = _adapter_registry().get("adapters") or {}
    adapter = adapters.get(plugin_source)
    if not isinstance(adapter, dict):
        return {}
    contract = adapter.get("recipe_contract")
    return contract if isinstance(contract, dict) else {}


def _recipe_path(artifact: dict[str, Any]) -> Path | None:
    for sidecar in artifact.get("sidecars") or []:
        if sidecar.get("label") == "recipe":
            href = sidecar.get("href")
            if isinstance(href, str) and href:
                return _resolve_sidecar(href)
    return None


def _parameter_sources(artifact: dict[str, Any]) -> dict[str, Any]:
    contract = artifact.get("original_artifact_contract") or {}
    plugin_source = str(artifact.get("plugin_source") or "")
    runtime_contract = _runtime_recipe_contract(plugin_source)
    recipe = {}
    recipe_path = _recipe_path(artifact)
    if recipe_path is not None:
        recipe = _load_json(recipe_path)
    return {
        "artifact_label": artifact.get("label"),
        "capability_id": artifact.get("capability_id"),
        "plugin_source": plugin_source,
        "recipe_path": _display_path(recipe_path),
        "recipe_exists": bool(recipe_path and recipe_path.exists()),
        "available_paths": sorted(_flatten_available_paths(recipe)),
        "contract_parameters": sorted(_contract_parameters(contract)),
        "runtime_contract_paths": sorted(
            str(path) for path in runtime_contract.get("accepted_paths") or []
        ),
        "runtime_contract_parameters": sorted(
            str(parameter)
            for parameter in runtime_contract.get("accepted_parameters") or []
        ),
        "runtime_contract_verified_by": list(runtime_contract.get("verified_by") or []),
    }


def _required_manifest_roles(capability: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every capability role, preserving required versus optional status."""

    roles: list[dict[str, Any]] = []
    period_semantics = capability.get("period_semantics") or {}
    period_role = period_semantics.get("role")
    period_required = bool(
        period_semantics.get("requires_period_column", period_role != "none")
    )
    if period_role in {"axis", "axis_or_table"}:
        roles.append(
            {
                "kind": "period",
                "role": "period_axis",
                "required": period_required,
            }
        )
    elif period_role == "filter":
        roles.append(
            {
                "kind": "period",
                "role": "period_filter",
                "required": period_required,
            }
        )

    metric_requirements = capability.get("metric_requirements") or {}
    for role in metric_requirements.get("source_metric_roles") or []:
        role_name = role.get("role")
        if isinstance(role_name, str):
            roles.append(
                {
                    "kind": "metric",
                    "role": role_name,
                    "required": bool(role.get("required", True)),
                }
            )

    dimensions = (
        (capability.get("selection_contract") or {}).get("dataset_requirements") or {}
    ).get("dimensions") or {}
    for role_name in dimensions.get("required_roles") or []:
        if isinstance(role_name, str):
            roles.append({"kind": "dimension", "role": role_name, "required": True})
    for role_name in dimensions.get("optional_roles") or []:
        if isinstance(role_name, str):
            roles.append({"kind": "dimension", "role": role_name, "required": False})

    return roles


def _artifact_variant_roles(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    variant = artifact.get("rendering_variant") or {}
    roles: list[dict[str, Any]] = []
    for role_name in variant.get("adds_parameter_roles") or []:
        if isinstance(role_name, str):
            roles.append({"kind": "variant", "role": role_name, "required": True})
    return roles


def _matches_candidate(
    candidate: dict[str, Any],
    *,
    available_paths: set[str],
    contract_parameters: set[str],
) -> bool:
    if "paths" in candidate:
        paths = [str(path) for path in candidate["paths"]]
        if candidate.get("kind") == "compound":
            return all(path in available_paths for path in paths)
        return any(path in available_paths for path in paths)
    if "parameters" in candidate:
        return any(
            str(parameter) in contract_parameters
            for parameter in candidate["parameters"]
        )
    return False


def _role_mapping(
    role: dict[str, Any],
    sources: list[dict[str, Any]],
    resolved_roles: dict[str, dict[str, Any]] | None = None,
    capability_id: str | None = None,
) -> dict[str, Any]:
    role_name = role["role"]
    capability_candidates = CAPABILITY_ROLE_PARAMETER_CANDIDATES.get(
        str(capability_id or ""), {}
    )
    candidates = capability_candidates.get(
        role_name, ROLE_PARAMETER_CANDIDATES.get(role_name, [])
    )
    if not candidates:
        return {
            **role,
            "status": "missing",
            "mapping_kind": None,
            "evidence": [],
            "issue": "no_role_parameter_candidates",
        }

    for candidate in candidates:
        if candidate.get("kind") == "runtime_contract":
            return {
                **role,
                "status": "mapped",
                "mapping_kind": "runtime_contract",
                "evidence": [
                    {
                        "artifact_label": None,
                        "recipe_path": None,
                        "paths": candidate.get("paths", []),
                        "parameters": candidate.get("parameters", []),
                        "source": "verified_runtime_contract",
                        "verified_by": candidate.get("verified_by"),
                    }
                ],
            }
        if candidate.get("kind") == "derived_from_period":
            source_role = str(candidate["role"])
            source_mapping = (resolved_roles or {}).get(source_role) or _role_mapping(
                {"kind": "period", "role": source_role},
                sources,
                resolved_roles=resolved_roles,
                capability_id=capability_id,
            )
            if source_mapping["status"] == "mapped":
                return {
                    **role,
                    "status": "mapped",
                    "mapping_kind": "derived_from_period",
                    "evidence": source_mapping["evidence"],
                    "depends_on_role": source_role,
                }

    for source in sources:
        gallery_paths = set(source.get("available_paths") or [])
        runtime_paths = set(source.get("runtime_contract_paths") or [])
        available_paths = gallery_paths | runtime_paths
        artifact_parameters = set(source.get("contract_parameters") or [])
        runtime_parameters = set(source.get("runtime_contract_parameters") or [])
        contract_parameters = artifact_parameters | runtime_parameters
        for candidate in candidates:
            if candidate.get("kind") == "derived_from_period":
                continue
            if candidate.get("kind") == "runtime_contract":
                continue
            if _matches_candidate(
                candidate,
                available_paths=available_paths,
                contract_parameters=contract_parameters,
            ):
                runtime_match = bool(
                    set(candidate.get("paths") or []) & runtime_paths
                    or set(candidate.get("parameters") or []) & runtime_parameters
                )
                return {
                    **role,
                    "status": "mapped",
                    "mapping_kind": candidate.get("kind"),
                    "evidence": [
                        {
                            "artifact_label": source.get("artifact_label"),
                            "recipe_path": (
                                None if runtime_match else source.get("recipe_path")
                            ),
                            "paths": candidate.get("paths", []),
                            "parameters": candidate.get("parameters", []),
                            "source": (
                                "verified_runtime_contract"
                                if runtime_match
                                else "gallery_or_artifact_contract"
                            ),
                            "verified_by": source.get(
                                "runtime_contract_verified_by", []
                            ),
                        }
                    ],
                }

    return {
        **role,
        "status": "missing",
        "mapping_kind": None,
        "evidence": [],
        "issue": "no_matching_parameter_evidence",
    }


def _role_key(role: dict[str, Any]) -> tuple[str, str]:
    return role["kind"], role["role"]


def _dedupe_roles(roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for role in roles:
        deduped.setdefault(_role_key(role), role)
    return list(deduped.values())


def _capability_audit(
    capability_id: str,
    capability: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    sources = [_parameter_sources(artifact) for artifact in artifacts]
    required_roles = _dedupe_roles(_required_manifest_roles(capability))
    resolved: dict[str, dict[str, Any]] = {}
    role_mappings: list[dict[str, Any]] = []
    for role in required_roles:
        mapping = _role_mapping(
            role,
            sources,
            resolved_roles=resolved,
            capability_id=capability_id,
        )
        role_mappings.append(mapping)
        resolved[role["role"]] = mapping

    variant_mappings: list[dict[str, Any]] = []
    for artifact in artifacts:
        for role in _artifact_variant_roles(artifact):
            mapping = _role_mapping(
                role,
                [_parameter_sources(artifact)],
                capability_id=capability_id,
            )
            mapping["artifact_label"] = artifact.get("label")
            variant_mappings.append(mapping)

    missing_roles = [
        mapping
        for mapping in role_mappings + variant_mappings
        if mapping["status"] != "mapped"
    ]
    if not artifacts:
        status = "missing_artifact_evidence"
    elif missing_roles:
        status = "parameter_contract_gap"
    else:
        status = "parameter_contract_ready"

    return {
        "capability_id": capability_id,
        "family": capability.get("family"),
        "status": status,
        "artifact_labels": [artifact.get("label") for artifact in artifacts],
        "role_mappings": role_mappings,
        "variant_role_mappings": variant_mappings,
        "missing_roles": missing_roles,
        "parameter_sources": sources,
    }


def _parameter_targets(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for evidence in mapping.get("evidence") or []:
        recipe_path = evidence.get("recipe_path")
        for path in evidence.get("paths") or []:
            targets.append(
                {
                    "target_type": "recipe_path",
                    "target": path,
                    "recipe_path": recipe_path,
                }
            )
        for parameter in evidence.get("parameters") or []:
            targets.append(
                {
                    "target_type": "artifact_contract_parameter",
                    "target": parameter,
                    "recipe_path": recipe_path,
                }
            )
    return targets


def _normalized_role_contract(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": mapping["kind"],
        "role": mapping["role"],
        "required": bool(mapping.get("required", True)),
        "status": mapping["status"],
        "mapping_kind": mapping.get("mapping_kind"),
        "caller_binding_required": not bool(mapping.get("depends_on_role")),
        "parameter_targets": _parameter_targets(mapping),
        "depends_on_role": mapping.get("depends_on_role"),
        "issue": mapping.get("issue"),
        "artifact_label": mapping.get("artifact_label"),
    }


def build_normalized_invocation_contract(
    capability_id: str,
    capability: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an exact role-to-parameter contract for one capability.

    This deterministic contract is justified because it only checks explicit
    manifest roles against concrete recipe/catalog/artifact parameter evidence.
    It does not decide semantic validity or choose columns for a user question.
    """

    audit = _capability_audit(capability_id, capability, artifacts)
    artifact_contracts: list[dict[str, Any]] = []
    for artifact in artifacts:
        variant_roles = _dedupe_roles(_artifact_variant_roles(artifact))
        sources = [_parameter_sources(artifact)]
        mappings = [
            _normalized_role_contract(
                _role_mapping(role, sources, capability_id=capability_id)
            )
            for role in variant_roles
        ]
        missing = [mapping for mapping in mappings if mapping["status"] != "mapped"]
        variant = artifact.get("rendering_variant") or {}
        artifact_contracts.append(
            {
                "artifact_label": artifact.get("label"),
                "plugin_source": artifact.get("plugin_source"),
                "output_form": variant.get("output_form"),
                "selector_level": variant.get("selector_level"),
                "layout_variant": variant.get("layout_variant"),
                "encoding_variant": variant.get("encoding_variant"),
                "variant_changes_capability_selection": variant.get(
                    "variant_changes_capability_selection"
                ),
                "status": (
                    "parameter_contract_ready"
                    if not missing
                    else "parameter_contract_gap"
                ),
                "variant_role_contracts": mappings,
                "missing_variant_roles": missing,
            }
        )

    role_contracts = [
        _normalized_role_contract(mapping) for mapping in audit["role_mappings"]
    ]
    required_role_contracts = [
        contract for contract in role_contracts if contract["required"]
    ]
    optional_role_contracts = [
        contract for contract in role_contracts if not contract["required"]
    ]
    variant_role_contracts = [
        _normalized_role_contract(mapping) for mapping in audit["variant_role_mappings"]
    ]
    plugin_sources = sorted(
        {
            str(artifact.get("plugin_source"))
            for artifact in artifacts
            if artifact.get("plugin_source")
        }
    )
    output_forms = sorted(
        {
            str((artifact.get("rendering_variant") or {}).get("output_form"))
            for artifact in artifacts
            if (artifact.get("rendering_variant") or {}).get("output_form")
        }
    )
    missing_roles = [
        _normalized_role_contract(mapping) for mapping in audit["missing_roles"]
    ]
    return {
        "schema_version": "0.1",
        "status": audit["status"],
        "capability_id": capability_id,
        "plugin_sources": plugin_sources,
        "artifact_labels": audit["artifact_labels"],
        "output_forms": output_forms,
        "required_role_contracts": required_role_contracts,
        "optional_role_contracts": optional_role_contracts,
        "variant_role_contracts": variant_role_contracts,
        "artifact_invocation_contracts": artifact_contracts,
        "missing_roles": missing_roles,
        "parameter_source_count": len(audit["parameter_sources"]),
        "boundary": (
            "Mechanical invocation contract only. It proves role-to-parameter "
            "evidence; it does not select semantically valid columns."
        ),
    }


def _used_roles_by_capability(
    capabilities: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    used: dict[str, set[str]] = defaultdict(set)
    for capability_id, capability in capabilities.items():
        for role in _required_manifest_roles(capability):
            used[role["role"]].add(capability_id)
    return used


def _used_roles_by_artifact(artifacts: list[dict[str, Any]]) -> dict[str, set[str]]:
    used: dict[str, set[str]] = defaultdict(set)
    for artifact in artifacts:
        label = str(artifact.get("label") or "")
        for role in _artifact_variant_roles(artifact):
            used[role["role"]].add(label)
    return used


def _role_kinds_for_capabilities(
    capabilities: dict[str, dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> dict[str, set[str]]:
    kinds: dict[str, set[str]] = defaultdict(set)
    for capability in capabilities.values():
        for role in _required_manifest_roles(capability):
            kinds[role["role"]].add(role["kind"])
    for artifact in artifacts:
        for role in _artifact_variant_roles(artifact):
            kinds[role["role"]].add(role["kind"])
    return kinds


def build_role_registry(
    capabilities: dict[str, dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical mechanical role registry used by manifest audits."""

    used_capabilities = _used_roles_by_capability(capabilities)
    used_artifacts = _used_roles_by_artifact(artifacts)
    role_kinds = _role_kinds_for_capabilities(capabilities, artifacts)
    all_chart_roles = sorted(
        set(ROLE_PARAMETER_CANDIDATES) | set(used_capabilities) | set(used_artifacts)
    )
    chart_roles = {
        role: {
            "role": role,
            "kinds": sorted(role_kinds.get(role) or []),
            "parameter_candidates": ROLE_PARAMETER_CANDIDATES.get(role, []),
            "used_by_capabilities": sorted(used_capabilities.get(role) or []),
            "used_by_artifacts": sorted(used_artifacts.get(role) or []),
            "registry_status": (
                "defined" if role in ROLE_PARAMETER_CANDIDATES else "missing_mapping"
            ),
        }
        for role in all_chart_roles
    }
    return {
        "schema_version": "0.1",
        "purpose": (
            "Canonical mechanical role vocabulary for chart selection. These "
            "roles constrain dataset/profile and plugin-parameter matching; "
            "they do not decide analysis validity."
        ),
        "chart_roles": chart_roles,
        "profile_roles": PROFILE_ROLE_DEFINITIONS,
        "capability_parameter_overrides": CAPABILITY_ROLE_PARAMETER_CANDIDATES,
        "counts": {
            "chart_roles": len(chart_roles),
            "profile_roles": len(PROFILE_ROLE_DEFINITIONS),
            "used_chart_roles": len(set(used_capabilities) | set(used_artifacts)),
            "chart_roles_missing_mapping": sum(
                1
                for role in set(used_capabilities) | set(used_artifacts)
                if role not in ROLE_PARAMETER_CANDIDATES
            ),
        },
    }


def audit_chart_plugin_parameter_contract(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    capabilities = manifest.get("capabilities") or {}
    artifacts = manifest.get("artifacts") or []
    if not isinstance(capabilities, dict):
        raise ValueError("selection manifest capabilities must be an object")
    if not isinstance(artifacts, list):
        raise ValueError("selection manifest artifacts must be a list")

    artifacts_by_capability: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        capability_id = artifact.get("capability_id")
        if isinstance(capability_id, str) and capability_id:
            artifacts_by_capability[capability_id].append(artifact)

    results = [
        _capability_audit(
            capability_id,
            capability,
            artifacts_by_capability.get(capability_id, []),
        )
        for capability_id, capability in sorted(capabilities.items())
        if isinstance(capability, dict)
    ]
    status_counts = Counter(result["status"] for result in results)
    missing_role_counts = Counter(
        missing["role"]
        for result in results
        for missing in result.get("missing_roles") or []
    )
    mapping_kind_counts = Counter(
        mapping.get("mapping_kind")
        for result in results
        for mapping in result.get("role_mappings", [])
        + result.get("variant_role_mappings", [])
        if mapping.get("status") == "mapped"
    )

    payload = {
        "purpose": (
            "Audit whether chart-selection manifest roles map to concrete "
            "plugin recipe, catalog, or artifact-contract parameters."
        ),
        "inputs": {"selection_manifest": str(selection_manifest_path)},
        "role_registry": build_role_registry(capabilities, artifacts),
        "counts": {
            "capabilities": len(results),
            "parameter_contract_ready": status_counts["parameter_contract_ready"],
            "parameter_contract_gap": status_counts["parameter_contract_gap"],
            "missing_artifact_evidence": status_counts["missing_artifact_evidence"],
        },
        "mapping_kind_counts": dict(sorted(mapping_kind_counts.items())),
        "missing_role_counts": dict(sorted(missing_role_counts.items())),
        "results": results,
        "normalized_invocation_contracts": {
            capability_id: build_normalized_invocation_contract(
                capability_id,
                capability,
                artifacts_by_capability.get(capability_id, []),
            )
            for capability_id, capability in sorted(capabilities.items())
            if isinstance(capability, dict)
        },
    }

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    output_md_path.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Chart Plugin Parameter Contract Audit",
        "",
        payload["purpose"],
        "",
        "## Counts",
        "",
    ]
    for key, value in counts.items():
        lines.append(f"- `{key}`: `{value}`")
    role_registry_counts = (payload.get("role_registry") or {}).get("counts") or {}
    lines.extend(["", "## Role Registry", ""])
    for key, value in role_registry_counts.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Mapping Kinds", ""])
    for key, value in (payload.get("mapping_kind_counts") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Missing Roles", ""])
    missing = payload.get("missing_role_counts") or {}
    if not missing:
        lines.append("- None")
    else:
        for key, value in missing.items():
            lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Capability Results", ""])
    for result in payload["results"]:
        status = result["status"]
        capability_id = result["capability_id"]
        lines.append(f"- `{capability_id}`: `{status}`")
        for missing_role in result.get("missing_roles") or []:
            lines.append(
                "  - missing "
                f"`{missing_role['kind']}.{missing_role['role']}`: "
                f"{missing_role.get('issue', 'missing parameter evidence')}"
            )
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=DEFAULT_SELECTION_MANIFEST,
        help="Selection manifest JSON path.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="Output JSON audit path.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Output Markdown audit path.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper()))
    payload = audit_chart_plugin_parameter_contract(
        selection_manifest_path=args.selection_manifest,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )
    logging.info("wrote %s", args.output_json)
    logging.info("wrote %s", args.output_md)
    return 0 if payload["counts"]["parameter_contract_gap"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
