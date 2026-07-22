"""Render one reporting manifest capability through Clara reporting-engine."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reporting_adapters import (
    load_manifest,
    prepare_invocation_plan,
    reporting_engine_root,
    resolve_capability_adapter,
)

__all__ = [
    "RenderRequest",
    "artifact_files",
    "build_render_recipe",
    "capability_render_proof",
    "capability_chart_options",
    "capability_option_overrides",
    "render_capability",
    "main",
]


ARTIFACT_MODE_DATA_ONLY = "data_only"
ARTIFACT_MODE_DATA_AND_RENDER = "data_and_render"
ARTIFACT_MODES = {ARTIFACT_MODE_DATA_ONLY, ARTIFACT_MODE_DATA_AND_RENDER}
RUNNER_BY_COMPONENT = {
    "distribution-analysis": "scripts/run_distribution.py",
    "funnel-analysis": "scripts/run_funnel_analysis.py",
    "mix-contribution-analysis": "scripts/run_mix_contribution.py",
    "period-comparison": "scripts/run_period_comparison.py",
    "scatter-bubble-analysis": "scripts/run_scatter_bubble.py",
    "set-overlap-analysis": "scripts/run_set_overlap.py",
    "statement-analysis": "scripts/run_statement_analysis.py",
    "variance-analysis": "scripts/run_variance.py",
}
COMPONENTS_WITH_CURRENCY = {
    "distribution-analysis",
    "mix-contribution-analysis",
    "period-comparison",
    "scatter-bubble-analysis",
    "variance-analysis",
}
COMPONENTS_WITH_ARTIFACT_MODE = {
    "distribution-analysis",
    "mix-contribution-analysis",
    "period-comparison",
    "scatter-bubble-analysis",
    "set-overlap-analysis",
    "variance-analysis",
}
PERIOD_SCOPE_OPTION_KEYS = {
    "selected_period",
    "selected_periods",
    "period_selection",
    "period_type",
    "period_grain",
    "period_comparison_mode",
    "period_window",
    "fiscal_start_month",
    "rolling_window_months",
    "rolling_window_days",
    "current_period_label",
    "previous_period_label",
}
PERIOD_SCOPE_BINDING_ROLES = (
    "period_scope",
    "analysis_period",
    "comparison_window",
    "period_filter",
    "period_axis",
)
EXPLICIT_ALL_DATA_VALUES = {
    "all",
    "all_available_data",
    "all_available_records",
    "all_data",
    "all_periods",
    "unfiltered",
}


@dataclass(frozen=True)
class RenderRequest:
    """Concrete request for one Clara reporting-engine render."""

    capability_id: str
    input_file: Path
    output_dir: Path
    recipe_path: Path | None = None
    dataset_profile: dict[str, Any] | None = None
    role_bindings: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    language: str = "en"
    currency: str | None = None
    artifact_mode: str = ARTIFACT_MODE_DATA_AND_RENDER
    include_variants: bool = False


RENDERED_ARTIFACT_SUFFIXES = {".html", ".pdf", ".png", ".svg"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _deep_set(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    current = payload
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _deep_get(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _append_unique(values: list[Any], additions: list[Any]) -> list[Any]:
    result = list(values)
    for item in additions:
        if item not in result:
            result.append(item)
    return result


def _binding_for_role(role_bindings: dict[str, Any], role: str) -> Any:
    if role in role_bindings:
        return role_bindings[role]
    aliases = {
        "primary_metric": "comparison_metric",
        "comparison_metric": "primary_metric",
        "variance_metric": "comparison_metric",
        "value_metric": "comparison_metric",
        "period_filter": "period_axis",
        "period_axis": "period_filter",
        "component_dimension": "dimension_member",
        "category": "dimension_member",
        "component_category": "dimension_member",
        "point_dimension": "dimension_member",
        "parent_driver": "dimension_member",
        "child_driver": "panel_dimension",
    }
    alias = aliases.get(role)
    if alias is not None and alias in role_bindings:
        return role_bindings[alias]
    return None


def _target_value(
    binding: Any,
    target: str,
    *,
    allow_shared_value: bool = True,
) -> Any:
    if isinstance(binding, dict):
        if target in binding:
            return binding[target]
        target_key = target.split(".")[-1]
        if target_key in binding:
            return binding[target_key]
        if allow_shared_value and "value" in binding:
            return binding["value"]
        return None
    return binding if allow_shared_value else None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return True


def _required_role_audit(
    *,
    base_recipe: dict[str, Any],
    effective_recipe: dict[str, Any],
    role_contracts: list[dict[str, Any]],
    role_bindings: dict[str, Any],
) -> dict[str, Any]:
    """Verify explicit caller bindings because required roles are mechanical."""

    records: list[dict[str, Any]] = []
    for contract in role_contracts:
        if not contract.get("required", True) or not contract.get(
            "caller_binding_required", True
        ):
            continue
        role = str(contract.get("role") or "")
        if not role:
            continue
        targets = [
            str(target.get("target") or "")
            for target in contract.get("parameter_targets") or []
            if not target.get("scope_control") and target.get("target")
        ]
        binding = _binding_for_role(role_bindings, role)
        is_compound = contract.get("mapping_kind") == "compound"
        source = "missing"
        if contract.get("mapping_kind") == "package_contract":
            package_value = (
                role_bindings.get("package_dir")
                or role_bindings.get("attribute_package_dir")
                or _deep_get(base_recipe, "package_dir")
            )
            missing_targets = [] if _has_value(package_value) else targets
            if not missing_targets:
                source = (
                    "role_bindings"
                    if _has_value(
                        role_bindings.get("package_dir")
                        or role_bindings.get("attribute_package_dir")
                    )
                    else "recipe"
                )
        elif _has_value(binding):
            missing_targets = [
                target
                for target in targets
                if not _has_value(
                    _target_value(
                        binding,
                        target,
                        allow_shared_value=not is_compound,
                    )
                )
                or not _has_value(_deep_get(effective_recipe, target))
            ]
            if not missing_targets:
                source = "role_bindings"
        elif base_recipe:
            missing_targets = [
                target
                for target in targets
                if not _has_value(_deep_get(base_recipe, target))
            ]
            if not missing_targets:
                source = "recipe"
        else:
            missing_targets = targets or ["explicit_role_binding"]
        records.append(
            {
                "role": role,
                "status": "satisfied" if not missing_targets else "missing",
                "source": source,
                "required_targets": targets,
                "missing_targets": missing_targets,
            }
        )
    missing_roles = [
        str(record["role"]) for record in records if record["status"] == "missing"
    ]
    return {
        "status": "satisfied" if not missing_roles else "missing_required_roles",
        "missing_roles": missing_roles,
        "roles": records,
    }


def _apply_role_contracts(
    recipe: dict[str, Any],
    role_contracts: list[dict[str, Any]],
    role_bindings: dict[str, Any],
) -> dict[str, list[str]]:
    applied: dict[str, list[str]] = {}
    for contract in role_contracts:
        if contract.get("depends_on_role"):
            continue
        role = str(contract.get("role") or "")
        if not role:
            continue
        binding = _binding_for_role(role_bindings, role)
        if binding is None:
            continue
        is_compound = contract.get("mapping_kind") == "compound"
        for target in contract.get("parameter_targets") or []:
            if target.get("scope_control"):
                continue
            target_path = str(target.get("target") or "")
            if not target_path or target_path == "package_dir":
                continue
            value = _target_value(
                binding,
                target_path,
                allow_shared_value=not is_compound,
            )
            if value is None:
                continue
            if target_path == "mappings.dimensions":
                existing = _as_list(_deep_get(recipe, target_path))
                _deep_set(
                    recipe,
                    target_path,
                    _append_unique(existing, [str(item) for item in _as_list(value)]),
                )
            else:
                _deep_set(recipe, target_path, value)
            applied.setdefault(role, []).append(target_path)
    return applied


def _apply_period_scope_bindings(
    recipe: dict[str, Any],
    role_bindings: dict[str, Any],
    capability: dict[str, Any],
) -> dict[str, list[str]]:
    applied: dict[str, list[str]] = {}
    applied_targets: set[tuple[str, str]] = set()
    allowed_targets = set(
        (capability.get("period_scope_contract") or {}).get("accepted_scope_controls")
        or []
    )
    period_role = str(
        (capability.get("period_scope_contract") or {}).get("role") or "none"
    )
    for role in PERIOD_SCOPE_BINDING_ROLES:
        if role == "period_filter" and period_role != "filter":
            continue
        if role == "period_axis" and period_role not in {"axis", "axis_or_table"}:
            continue
        binding = role_bindings.get(role)
        if binding is None and role in {"period_filter", "period_axis"}:
            binding = _binding_for_role(role_bindings, role)
        if binding is None:
            continue
        if isinstance(binding, dict):
            for key in sorted(PERIOD_SCOPE_OPTION_KEYS):
                if key not in binding:
                    continue
                target_path = f"options.{key}"
                if target_path not in allowed_targets:
                    continue
                if (role, target_path) in applied_targets:
                    continue
                recipe.setdefault("options", {})[key] = binding[key]
                applied.setdefault(role, []).append(target_path)
                applied_targets.add((role, target_path))
            if (
                "filters" in binding
                and "filters" in allowed_targets
                and (role, "filters") not in applied_targets
            ):
                recipe["filters"] = binding["filters"]
                applied.setdefault(role, []).append("filters")
                applied_targets.add((role, "filters"))
            for target_path in sorted(allowed_targets):
                if "." in target_path or target_path == "filters":
                    continue
                if target_path not in binding:
                    continue
                recipe[target_path] = binding[target_path]
                applied.setdefault(role, []).append(target_path)
            continue
        if role in {"period_scope", "analysis_period", "comparison_window"}:
            target_path = "options.selected_periods"
            if target_path in allowed_targets:
                recipe.setdefault("options", {})["selected_periods"] = _as_list(binding)
                applied.setdefault(role, []).append(target_path)
    return applied


def _has_scope_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return True


def _is_explicit_all_data(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in EXPLICIT_ALL_DATA_VALUES
    if isinstance(value, list | tuple | set):
        normalized = {str(item).strip().lower() for item in value}
        return bool(normalized & EXPLICIT_ALL_DATA_VALUES)
    return False


def _is_bounding_period_type(value: Any) -> bool:
    """Return whether a period mode mechanically selects finite date windows."""

    normalized = "".join(
        character for character in str(value).lower() if character.isalnum()
    )
    return normalized in {
        "fiscalyeartodate",
        "fytd",
        "l12m",
        "periodtodate",
        "rolling",
        "rollingperiod",
        "rollingwindow",
        "r12m",
        "todate",
        "yeartodate",
        "ytd",
    }


def _period_scope_audit(
    capability: dict[str, Any],
    recipe: dict[str, Any],
    applied_scope_roles: dict[str, list[str]],
) -> dict[str, Any]:
    scope_contract = capability.get("period_scope_contract") or {}
    period_role = str(
        scope_contract.get("role")
        or (capability.get("period_semantics") or {}).get("role")
        or "none"
    )
    period_column_required = bool(
        scope_contract.get("period_column_required", period_role != "none")
    )
    comparison_pair_required = bool(
        scope_contract.get("comparison_pair_required_for_render", False)
    )
    if period_role == "none":
        return {
            "status": "not_applicable",
            "role": period_role,
            "severity": "none",
            "period_column_required": False,
            "comparison_pair_required_for_render": False,
            "scope_required_for_render": False,
            "scope_option_paths": [],
            "applied_scope_roles": applied_scope_roles,
            "message": "Capability does not use period filtering or a period axis.",
        }

    options = recipe.get("options") if isinstance(recipe.get("options"), dict) else {}
    accepted_scope_controls = set(scope_contract.get("accepted_scope_controls") or [])
    accepted_option_keys = {
        path.split(".", 1)[1]
        for path in accepted_scope_controls
        if path.startswith("options.")
    }
    accepted_root_keys = {
        path
        for path in accepted_scope_controls
        if "." not in path and path != "filters"
    }
    scope_option_paths = [
        f"options.{key}"
        for key in sorted(accepted_option_keys)
        if _has_scope_value(options.get(key))
    ]
    if "filters" in accepted_scope_controls and _has_scope_value(recipe.get("filters")):
        scope_option_paths.append("filters")
    if "options.filters" in accepted_scope_controls and _has_scope_value(
        options.get("filters")
    ):
        scope_option_paths.append("options.filters")
    scope_option_paths.extend(
        key for key in sorted(accepted_root_keys) if _has_scope_value(recipe.get(key))
    )
    bounded_scope_option_paths = [
        path
        for path in scope_option_paths
        if path
        in {
            "filters",
            "options.filters",
            "options.period_selection",
            "options.period_window",
            "options.rolling_window_days",
            "options.rolling_window_months",
            "options.selected_period",
            "options.selected_periods",
        }
    ]
    for key in ("period_type", "period_comparison_mode"):
        path = f"options.{key}"
        if path in accepted_scope_controls and _is_bounding_period_type(
            options.get(key)
        ):
            bounded_scope_option_paths.append(path)
    explicit_all_data = any(
        _is_explicit_all_data(options.get(key)) for key in accepted_option_keys
    ) or any(_is_explicit_all_data(recipe.get(key)) for key in accepted_root_keys)
    mappings = (
        recipe.get("mappings") if isinstance(recipe.get("mappings"), dict) else {}
    )
    period_column_mapped = any(
        _has_scope_value(mappings.get(key)) for key in ("date_column", "period_column")
    )
    current_period = (
        options.get("current_period_label")
        or options.get("current_period")
        or mappings.get("comparison_period")
    )
    previous_period = (
        options.get("previous_period_label")
        or options.get("previous_period")
        or options.get("comparison_period")
        or options.get("baseline_period")
        or mappings.get("baseline_period")
    )
    comparison_pair_bound = bool(
        _has_scope_value(current_period)
        and _has_scope_value(previous_period)
        and str(current_period) != str(previous_period)
    )
    if comparison_pair_required and comparison_pair_bound:
        bounded_scope_option_paths.append("comparison_pair")
    if comparison_pair_required and not comparison_pair_bound:
        status = "missing_required_comparison_pair"
        severity = "error"
        message = (
            "Capability requires distinct current and baseline period bindings "
            "before rendering."
        )
    elif explicit_all_data:
        status = "explicit_all_data"
        severity = "none"
        message = "Caller explicitly requested all available periods."
    elif bounded_scope_option_paths:
        status = "explicit_scope"
        severity = "none"
        message = "Caller supplied a bounded period scope."
    elif (
        period_role == "filter"
        and not period_column_required
        and not period_column_mapped
    ):
        status = "optional_filter_not_used"
        severity = "none"
        message = (
            "No optional period column was bound; the chart will use all "
            "available records without period filtering."
        )
    elif scope_contract.get("scope_required_for_render"):
        status = "unscoped_filter_defaults_to_all_available_data"
        severity = "error"
        message = (
            "Capability uses a period filter and requires a bounded scope or "
            "an explicit all-data request before rendering."
        )
    else:
        status = "unscoped_period_axis_uses_available_range"
        severity = "info"
        message = (
            "Capability uses a period axis and no bounded period scope was "
            "provided; available periods will define the visible range."
        )
    return {
        "status": status,
        "role": period_role,
        "severity": severity,
        "period_column_required": period_column_required,
        "comparison_pair_required_for_render": comparison_pair_required,
        "comparison_pair_bound": comparison_pair_bound,
        "scope_required_for_render": bool(
            scope_contract.get("scope_required_for_render")
        ),
        "explicit_all_data_allowed": bool(
            scope_contract.get("explicit_all_data_allowed")
        ),
        "scope_option_paths": scope_option_paths,
        "bounded_scope_option_paths": bounded_scope_option_paths,
        "applied_scope_roles": applied_scope_roles,
        "unscoped_default": scope_contract.get("unscoped_default"),
        "message": message,
    }


def _render_contract(capability_id: str, *, root: Path | None = None) -> dict[str, Any]:
    capability = _capability_record(capability_id, root=root)
    contract = capability.get("render_contract") or {}
    if not isinstance(contract, dict):
        raise ValueError(f"Capability has no render contract: {capability_id}")
    return contract


def capability_chart_options(
    capability_id: str,
    *,
    include_variants: bool = False,
    root: Path | None = None,
) -> list[str]:
    """Return runner chart names for one manifest capability."""

    contract = _render_contract(capability_id, root=root)
    charts = list(contract.get("chart_options") or [])
    if include_variants:
        charts = _append_unique(
            charts, list(contract.get("variant_chart_options") or [])
        )
    return [str(chart) for chart in charts]


def capability_option_overrides(
    capability_id: str, *, root: Path | None = None
) -> dict[str, Any]:
    """Return runner option overrides for one capability."""

    return dict(
        _render_contract(capability_id, root=root).get("fixed_option_overrides") or {}
    )


def _capability_record(
    capability_id: str, *, root: Path | None = None
) -> dict[str, Any]:
    manifest = load_manifest(root)
    capabilities = manifest.get("capabilities") or {}
    capability = capabilities.get(capability_id)
    if not isinstance(capability, dict):
        raise KeyError(f"Unknown capability: {capability_id}")
    return capability


def _capability_contract(
    capability_id: str, *, root: Path | None = None
) -> dict[str, Any]:
    capability = _capability_record(capability_id, root=root)
    contract = capability.get("normalized_invocation_contract") or {}
    if not isinstance(contract, dict):
        raise ValueError(f"Capability has no invocation contract: {capability_id}")
    return contract


def build_render_recipe(
    request: RenderRequest,
    *,
    root: Path | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    """Write and return a generated recipe for one capability when needed."""

    base_recipe: dict[str, Any] = {}
    if request.recipe_path is not None:
        base_recipe = _load_json(request.recipe_path)
    role_bindings = dict(request.role_bindings or {})
    options = dict(request.options or {})
    recipe = deepcopy(base_recipe)
    recipe.setdefault("schema_version", "1.0")
    recipe["source_file"] = str(request.input_file)
    recipe["language"] = request.language
    recipe.setdefault("mappings", {})
    recipe.setdefault("options", {})
    for key, value in options.items():
        if "." in key:
            _deep_set(recipe, key, value)
        else:
            recipe["options"][key] = value
    if request.currency:
        recipe["options"]["currency"] = request.currency
    charts = capability_chart_options(
        request.capability_id,
        include_variants=request.include_variants,
        root=root,
    )
    if charts:
        recipe["options"]["charts"] = charts
        recipe["options"]["small_multiples"] = request.include_variants
    for key, value in capability_option_overrides(
        request.capability_id, root=root
    ).items():
        recipe["options"][key] = value
    capability = _capability_record(request.capability_id, root=root)
    contract = capability.get("normalized_invocation_contract") or {}
    if not isinstance(contract, dict):
        raise ValueError(
            f"Capability has no invocation contract: {request.capability_id}"
        )
    role_contracts = list(contract.get("required_role_contracts") or [])
    role_contracts += list(contract.get("optional_role_contracts") or [])
    if request.include_variants:
        role_contracts += list(contract.get("variant_role_contracts") or [])
    applied_roles = _apply_role_contracts(
        recipe,
        role_contracts,
        role_bindings,
    )
    applied_scope_roles = _apply_period_scope_bindings(
        recipe, role_bindings, capability
    )
    required_role_audit = _required_role_audit(
        base_recipe=base_recipe,
        effective_recipe=recipe,
        role_contracts=list(contract.get("required_role_contracts") or []),
        role_bindings=role_bindings,
    )
    period_scope_audit = _period_scope_audit(
        capability,
        recipe,
        applied_scope_roles,
    )
    if request.recipe_path is None and not role_bindings and not options and not charts:
        return None, {
            "status": "not_written_no_recipe_overrides",
            "charts": charts,
            "applied_roles": applied_roles,
            "applied_scope_roles": applied_scope_roles,
            "required_roles": required_role_audit,
            "period_scope": period_scope_audit,
            "option_overrides": capability_option_overrides(
                request.capability_id, root=root
            ),
        }
    generated_recipe_path = request.output_dir / "render_request_recipe.json"
    _write_json(generated_recipe_path, recipe)
    return generated_recipe_path, {
        "status": "written",
        "path": str(generated_recipe_path),
        "charts": charts,
        "applied_roles": applied_roles,
        "applied_scope_roles": applied_scope_roles,
        "required_roles": required_role_audit,
        "period_scope": period_scope_audit,
        "option_overrides": capability_option_overrides(
            request.capability_id, root=root
        ),
    }


def _enforce_render_preflight(recipe_audit: dict[str, Any]) -> None:
    """Stop execution when explicit mechanical render prerequisites fail."""

    failures: list[str] = []
    required_roles = recipe_audit.get("required_roles") or {}
    missing_roles = required_roles.get("missing_roles") or []
    if missing_roles:
        failures.append("missing required role bindings: " + ", ".join(missing_roles))
    period_scope = recipe_audit.get("period_scope") or {}
    if period_scope.get("severity") == "error":
        failures.append(str(period_scope.get("message") or "invalid period scope"))
    if failures:
        raise ValueError("Reporting render preflight failed: " + "; ".join(failures))


def _attribute_table_key(capability_id: str) -> str:
    return capability_id.split(".", 1)[1]


def _render_attribute_table(
    request: RenderRequest,
    adapter: dict[str, Any],
) -> dict[str, Any]:
    role_bindings = request.role_bindings or {}
    package_dir = role_bindings.get("package_dir")
    if package_dir is None:
        package_dir = role_bindings.get("attribute_package_dir")
    if package_dir is None:
        raise ValueError("Attribute table rendering requires package_dir role binding.")
    component_root = Path(str(adapter["component_root"]))
    vendor_root = component_root / "vendor"
    if vendor_root.is_dir():
        sys.path.insert(0, str(vendor_root))
    else:
        source_root = next(
            (
                parent
                for parent in SCRIPT_DIR.parents
                if (
                    parent / "modules" / "pdp" / "attribute_table_templates.py"
                ).is_file()
            ),
            SCRIPT_DIR.parents[2],
        )
        if (source_root / "modules" / "pdp" / "attribute_table_templates.py").is_file():
            sys.path.insert(0, str(source_root))
    from modules.pdp.attribute_table_templates import (  # noqa: PLC0415
        build_attribute_tables_from_package,
    )

    manifest = build_attribute_tables_from_package(
        Path(package_dir),
        output_dir=request.output_dir,
        table_keys=[_attribute_table_key(request.capability_id)],
        language=request.language,
    )
    return {
        "status": "ok",
        "runner_type": "attribute_table_builder",
        "returncode": 0,
        "manifest": manifest,
    }


def _runner_command(
    request: RenderRequest,
    *,
    component_root: Path,
    recipe_path: Path | None,
) -> list[str]:
    component = component_root.name
    runner = RUNNER_BY_COMPONENT.get(component)
    if runner is None:
        raise ValueError(f"No render runner registered for component: {component}")
    command = [
        sys.executable,
        str(component_root / runner),
        str(request.input_file),
        "--output-dir",
        str(request.output_dir),
        "--language",
        request.language,
    ]
    if recipe_path is not None:
        command.extend(["--recipe", str(recipe_path)])
    if request.currency and component in COMPONENTS_WITH_CURRENCY:
        command.extend(["--currency", request.currency])
    if component in COMPONENTS_WITH_ARTIFACT_MODE:
        artifact_mode = str(request.artifact_mode or ARTIFACT_MODE_DATA_AND_RENDER)
        if artifact_mode not in ARTIFACT_MODES:
            allowed = ", ".join(sorted(ARTIFACT_MODES))
            raise ValueError(
                f"Unsupported artifact_mode {artifact_mode!r}; use {allowed}."
            )
        command.extend(["--artifact-mode", artifact_mode])
    return command


def artifact_files(output_dir: Path) -> list[str]:
    """Return files written under an output directory."""

    if not output_dir.exists():
        return []
    return sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file()
    )


def _artifact_file_states(output_dir: Path) -> dict[str, tuple[int, int]]:
    """Return artifact modification state for current-run change detection."""

    if not output_dir.exists():
        return {}
    states: dict[str, tuple[int, int]] = {}
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        states[str(path.relative_to(output_dir))] = (stat.st_mtime_ns, stat.st_size)
    return states


def capability_render_proof(
    capability_id: str,
    artifacts: list[str],
    *,
    artifact_mode: str,
    include_variants: bool = False,
    role_bindings: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Prove that requested chart outputs, not only the runner, completed."""

    contract = _render_contract(capability_id, root=root)
    expected_tokens = list(contract.get("expected_artifact_stems") or [])
    if include_variants:
        capability = _capability_record(capability_id, root=root)
        invocation_contract = capability.get("normalized_invocation_contract") or {}
        variant_tokens = []
        for artifact_contract in (
            invocation_contract.get("artifact_invocation_contracts") or []
        ):
            if artifact_contract.get("selector_level") != "rendering_variant_choice":
                continue
            artifact_label = str(artifact_contract.get("artifact_label") or "")
            artifact_stem = artifact_label.rsplit("/", maxsplit=1)[-1].strip()
            if artifact_stem:
                variant_tokens.append(artifact_stem.replace(" ", "_"))
        expected_tokens = _append_unique(expected_tokens, variant_tokens)
    for template_contract in contract.get("expected_artifact_stem_templates") or []:
        role = str(template_contract.get("role") or "")
        binding = _binding_for_role(role_bindings or {}, role)
        binding_key = str(template_contract.get("binding_key") or "")
        if isinstance(binding, dict) and binding_key:
            binding = binding.get(binding_key)
        values = _as_list(binding)
        if not template_contract.get("for_each") and values:
            values = values[:1]
        template = str(template_contract.get("template") or "")
        expected_tokens.extend(
            template.format(value=value) for value in values if template
        )
    if artifact_mode != ARTIFACT_MODE_DATA_AND_RENDER:
        return {
            "status": "not_required_data_only",
            "expected_chart_tokens": expected_tokens,
            "rendered_artifacts": [],
            "missing_chart_tokens": [],
        }
    if not expected_tokens:
        return {
            "status": "not_configured",
            "expected_chart_tokens": [],
            "rendered_artifacts": [],
            "missing_chart_tokens": [],
        }
    rendered_artifacts = [
        artifact
        for artifact in artifacts
        if Path(artifact).suffix.casefold() in RENDERED_ARTIFACT_SUFFIXES
    ]
    normalized_artifacts = {
        artifact: Path(artifact).stem.casefold().replace("-", "_")
        for artifact in rendered_artifacts
    }
    normalized_expected = [
        token.casefold().replace("-", "_") for token in expected_tokens
    ]
    missing_tokens = [
        token
        for token, normalized_token in zip(expected_tokens, normalized_expected)
        if normalized_token not in normalized_artifacts.values()
    ]
    allowed_tokens = set(normalized_expected)
    allowed_tokens.update(
        str(token).casefold().replace("-", "_")
        for token in contract.get("allowed_support_artifact_stems") or []
    )
    unexpected_artifacts = [
        artifact
        for artifact, normalized in normalized_artifacts.items()
        if normalized not in allowed_tokens
    ]
    if missing_tokens:
        status = "missing_expected_render"
    elif unexpected_artifacts:
        status = "unexpected_rendered_artifacts"
    else:
        status = "rendered"
    return {
        "status": status,
        "expected_chart_tokens": expected_tokens,
        "rendered_artifacts": rendered_artifacts,
        "missing_chart_tokens": missing_tokens,
        "unexpected_rendered_artifacts": unexpected_artifacts,
    }


def render_capability(
    request: RenderRequest,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Render one capability through its Clara reporting adapter."""

    resolved_root = root or reporting_engine_root()
    request.output_dir.mkdir(parents=True, exist_ok=True)
    adapter = resolve_capability_adapter(request.capability_id, root=resolved_root)
    plan = prepare_invocation_plan(
        request.capability_id,
        dataset_profile=request.dataset_profile,
        root=resolved_root,
    )
    recipe_path, recipe_audit = build_render_recipe(request, root=resolved_root)
    _enforce_render_preflight(recipe_audit)
    artifacts_before = _artifact_file_states(request.output_dir)
    if adapter["component_name"] == "attribute-reporting":
        runner_result = _render_attribute_table(request, adapter)
        command: list[str] = []
    else:
        component_root = Path(str(adapter["component_root"]))
        command = _runner_command(
            request,
            component_root=component_root,
            recipe_path=recipe_path or request.recipe_path,
        )
        completed = subprocess.run(
            command,
            cwd=component_root,
            text=True,
            capture_output=True,
            check=False,
        )
        runner_result = {
            "status": "ok" if completed.returncode == 0 else "failed",
            "runner_type": "component_cli",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if completed.returncode != 0:
            manifest = {
                "schema_version": "0.1",
                "capability_id": request.capability_id,
                "adapter": adapter,
                "invocation_plan": plan,
                "recipe": recipe_audit,
                "command": command,
                "runner": runner_result,
                "artifacts": artifact_files(request.output_dir),
            }
            _write_json(request.output_dir / "render_manifest.json", manifest)
            manifest["artifacts"] = artifact_files(request.output_dir)
            _write_json(request.output_dir / "render_manifest.json", manifest)
            raise RuntimeError(
                "Reporting render failed for "
                f"{request.capability_id}: {completed.stderr.strip()}"
            )
    artifact_states = _artifact_file_states(request.output_dir)
    artifacts = sorted(artifact_states)
    current_run_artifacts = sorted(
        artifact
        for artifact, state in artifact_states.items()
        if artifacts_before.get(artifact) != state
    )
    render_proof = capability_render_proof(
        request.capability_id,
        current_run_artifacts,
        artifact_mode=request.artifact_mode,
        include_variants=request.include_variants,
        role_bindings=request.role_bindings,
        root=resolved_root,
    )
    manifest = {
        "schema_version": "0.1",
        "capability_id": request.capability_id,
        "owner": "clara.reporting-engine",
        "adapter_id": adapter["adapter_id"],
        "component_name": adapter["component_name"],
        "legacy_plugin_source": adapter["legacy_plugin_source"],
        "input_file": str(request.input_file),
        "output_dir": str(request.output_dir),
        "artifact_mode": request.artifact_mode,
        "include_variants": request.include_variants,
        "invocation_plan": plan,
        "recipe": recipe_audit,
        "command": command,
        "runner": runner_result,
        "artifacts": artifacts,
        "render_proof": render_proof,
        "boundary": (
            "Unified Clara reporting-engine render call. Semantic chart selection "
            "is outside this layer."
        ),
    }
    _write_json(request.output_dir / "render_manifest.json", manifest)
    manifest["artifacts"] = artifact_files(request.output_dir)
    _write_json(request.output_dir / "render_manifest.json", manifest)
    if render_proof.get("status") in {
        "missing_expected_render",
        "unexpected_rendered_artifacts",
    }:
        raise RuntimeError(
            "Reporting render proof failed for "
            f"{request.capability_id}: {render_proof.get('status')}"
        )
    return manifest


def _json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("JSON argument must be an object.")
    return payload


def main(argv: list[str] | None = None) -> int:
    """Render one capability from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capability_id")
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument(
        "--dataset-profile",
        type=Path,
        help="Mechanical dataset profile JSON used in the invocation audit.",
    )
    parser.add_argument("--role-bindings-json")
    parser.add_argument("--options-json")
    parser.add_argument("--language", default="en")
    parser.add_argument("--currency")
    parser.add_argument(
        "--artifact-mode",
        choices=sorted(ARTIFACT_MODES),
        default=ARTIFACT_MODE_DATA_AND_RENDER,
    )
    parser.add_argument("--include-variants", action="store_true")
    args = parser.parse_args(argv)
    request = RenderRequest(
        capability_id=args.capability_id,
        input_file=args.input_file,
        output_dir=args.output_dir,
        recipe_path=args.recipe,
        dataset_profile=(
            _load_json(args.dataset_profile) if args.dataset_profile else None
        ),
        role_bindings=_json_arg(args.role_bindings_json),
        options=_json_arg(args.options_json),
        language=args.language,
        currency=args.currency,
        artifact_mode=args.artifact_mode,
        include_variants=args.include_variants,
    )
    result = render_capability(request)
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
