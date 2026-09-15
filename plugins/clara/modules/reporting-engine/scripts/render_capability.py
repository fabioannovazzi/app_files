"""Render one reporting manifest capability through Clara reporting-engine."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

CLARA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(CLARA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CLARA_SCRIPTS))

from artifact_publication import publish_snapshot, verify_snapshot
from bounded_process import run_process
from dataset_snapshot import prepare_dataset_input
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
    "verify_render_generation",
    "write_json_receipt",
    "output_lock",
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
    timeout_seconds: int = 600
    parser_settings: dict[str, Any] | None = None


RENDERED_ARTIFACT_SUFFIXES = {".html", ".pdf", ".png", ".svg"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_json_receipt(path: Path, payload: dict[str, Any]) -> None:
    """Publish one JSON receipt atomically after flushing its file bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical_json_sha256(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_input_evidence(path: Path) -> dict[str, Any]:
    """Return exact file or directory evidence without changing source bytes."""

    resolved = path.expanduser().resolve()
    if resolved.is_file():
        return {
            "kind": "file",
            "path": str(resolved),
            "sha256": _sha256_file(resolved),
            "size_bytes": resolved.stat().st_size,
        }
    if resolved.is_dir():
        files = [
            {
                "path": item.relative_to(resolved).as_posix(),
                "sha256": _sha256_file(item),
                "size_bytes": item.stat().st_size,
            }
            for item in sorted(resolved.rglob("*"))
            if item.is_file()
        ]
        return {
            "kind": "directory",
            "path": str(resolved),
            "files": files,
            "inventory_sha256": _canonical_json_sha256(files),
        }
    raise ValueError(f"Reporting input does not exist: {resolved}")


def _output_evidence(
    output_dir: Path,
    artifacts: list[str],
) -> list[dict[str, Any]]:
    """Return byte-level evidence for current-run outputs."""

    records: list[dict[str, Any]] = []
    resolved_root = output_dir.resolve()
    for relative in sorted(set(artifacts)):
        path = (resolved_root / relative).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(
                f"Rendered artifact escapes output_dir: {relative}"
            ) from exc
        if not path.is_file():
            raise ValueError(f"Rendered artifact is missing: {relative}")
        records.append(
            {
                "path": relative,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def _render_request_evidence(request: RenderRequest) -> dict[str, Any]:
    payload = {
        "capability_id": request.capability_id,
        "role_bindings": request.role_bindings or {},
        "options": request.options or {},
        "language": request.language,
        "currency": request.currency,
        "artifact_mode": request.artifact_mode,
        "include_variants": request.include_variants,
        "parser_settings": request.parser_settings,
    }
    return {
        "contract": payload,
        "sha256": _canonical_json_sha256(payload),
    }


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
    write_json_receipt(generated_recipe_path, recipe)
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
    host_root = component_root.parent.parent
    launcher = host_root / "scripts" / "managed_python_runtime.py"
    if component_root.parent.name == "modules" and launcher.is_file():
        command = [
            sys.executable,
            str(launcher),
            "--module",
            component,
            "run",
            runner,
        ]
    else:
        command = [sys.executable, str(component_root / runner)]
    command.extend(
        [
            str(request.input_file),
            "--output-dir",
            str(request.output_dir),
            "--language",
            request.language,
        ]
    )
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
    """Return deliverables, excluding reserved runtime state and retained generations."""

    if not output_dir.exists():
        return []
    return sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
        and path.relative_to(output_dir).parts[0]
        not in {".reporting-generations", ".logs"}
        and path.relative_to(output_dir).as_posix()
        not in {".render.lock", "current_reporting.json"}
        and not re.fullmatch(
            r"render_manifest\.[0-9a-f]{32}\.previous\.json",
            path.relative_to(output_dir).as_posix(),
        )
    )


def _publish_run_artifacts(
    run_dir: Path,
    output_dir: Path,
    artifacts: list[str],
) -> None:
    """Copy only files created in an isolated run directory into output_dir."""

    resolved_run_dir = run_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    for relative in artifacts:
        source = resolved_run_dir / relative
        target = resolved_output_dir / relative
        if any(
            part.is_symlink()
            for part in (source, *source.parents)
            if part != resolved_run_dir.parent
        ):
            raise ValueError(f"Rendered artifact may not contain a symlink: {relative}")
        if any(
            part.is_symlink()
            for part in (target, *target.parents)
            if part != resolved_output_dir.parent
        ):
            raise ValueError(
                f"Rendered artifact target may not contain a symlink: {relative}"
            )
        try:
            source.relative_to(resolved_run_dir)
            target.relative_to(resolved_output_dir)
        except ValueError as exc:
            raise ValueError(
                f"Rendered artifact escapes its run directory: {relative}"
            ) from exc
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Rendered artifact is not a regular file: {relative}")
        if target.is_symlink():
            raise ValueError(
                f"Rendered artifact target may not be a symlink: {relative}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged:
            staged_path = Path(staged.name)
            try:
                with source.open("rb") as original:
                    shutil.copyfileobj(original, staged)
                staged.flush()
                os.fsync(staged.fileno())
            except BaseException:
                staged_path.unlink(missing_ok=True)
                raise
        try:
            os.replace(staged_path, target)
        finally:
            staged_path.unlink(missing_ok=True)


def _published_recipe_audit(
    recipe_audit: dict[str, Any],
    *,
    run_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], Path | None]:
    """Rebase a generated recipe audit from the isolated run to final output."""

    result = deepcopy(recipe_audit)
    raw_path = result.get("path")
    if not raw_path:
        return result, None
    recipe_path = Path(str(raw_path)).resolve()
    try:
        relative = recipe_path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise ValueError("Generated render recipe escaped its isolated run") from exc
    published = output_dir.resolve() / relative
    result["path"] = str(published)
    return result, published


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


@contextmanager
def _run_directory(parent: Path):
    """Retain complete staging evidence if a runner or publication is interrupted."""
    directory = Path(tempfile.mkdtemp(prefix=".clara-reporting-run-", dir=parent))
    completed = False
    try:
        yield str(directory)
        completed = True
    finally:
        if completed:
            shutil.rmtree(directory)


@contextmanager
def output_lock(directory: Path, *, name: str = ".render.lock"):
    """Serialize attempts so one run cannot overwrite another run's receipt."""
    directory.mkdir(parents=True, exist_ok=True)
    if Path(name).name != name:
        raise ValueError("Output lock name must be one filename")
    lock = directory / name
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or lock.is_symlink():
            raise ValueError("Render lock must be an ordinary single-link file")
        if os.name == "nt":
            import msvcrt

            if info.st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def render_capability(
    request: RenderRequest, *, root: Path | None = None
) -> dict[str, Any]:
    """Execute one serialized, receipt-bound reporting attempt."""
    with output_lock(request.output_dir):
        return _render_attempt(request, root=root)


def _render_attempt(
    request: RenderRequest, *, root: Path | None = None
) -> dict[str, Any]:
    """Invalidate stale success before a new attempt and retain terminal failures."""
    if request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = request.output_dir / "render_manifest.json"
    attempt_id = uuid.uuid4().hex
    previous = request.output_dir / f"render_manifest.{attempt_id}.previous.json"
    if receipt.is_file():
        shutil.copy2(receipt, previous)
    state = {
        "schema_version": "0.2",
        "capability_id": request.capability_id,
        "attempt_id": attempt_id,
        "status": "running",
        "runner": {"status": "running", "returncode": None},
    }
    write_json_receipt(receipt, state)
    write_json_receipt(request.output_dir / "current_reporting.json", state)
    complete = False
    try:
        result = _render_capability(request, root=root)
        result["attempt_id"] = attempt_id
        result["status"] = "completed"
        generation_root = request.output_dir / ".reporting-generations"
        if generation_root.is_symlink():
            raise ValueError(
                "Reporting generations directory must not be a symbolic link"
            )
        generation_root.mkdir(exist_ok=True)
        generation = generation_root / attempt_id
        generation.mkdir()
        snapshot_records = list(result["evidence"]["outputs"])
        recipe = result["evidence"]["recipe"]
        if recipe.get("kind") == "file":
            recipe_relative = (
                Path(recipe["path"])
                .resolve()
                .relative_to(request.output_dir.resolve())
                .as_posix()
            )
            if recipe_relative not in {item["path"] for item in snapshot_records}:
                snapshot_records.append({**recipe, "path": recipe_relative})
        result["evidence"]["snapshot_outputs"] = snapshot_records
        publish_snapshot(
            request.output_dir,
            generation,
            manifest=result,
            records=snapshot_records,
            manifest_name="render_manifest.json",
            pointer_name="current_reporting.json",
            status="completed",
        )
        write_json_receipt(receipt, result)
        complete = True
        return result
    finally:
        if not complete:
            current = _load_json(receipt)
            current["status"] = "failed_or_interrupted"
            error = sys.exc_info()[1]
            current["failure"] = {
                "type": type(error).__name__,
                "message": str(error)[:4000],
                "logs": str(request.output_dir / ".logs"),
            }
            current.setdefault("runner", {})["status"] = "failed"
            write_json_receipt(receipt, current)
            write_json_receipt(request.output_dir / "current_reporting.json", current)


def verify_render_generation(output_dir: Path) -> dict[str, Any]:
    """Verify the complete published reporting generation."""
    return verify_snapshot(
        output_dir,
        pointer_name="current_reporting.json",
        status="completed",
        output_field=("evidence", "snapshot_outputs"),
    )


def _render_capability(
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
    with (
        tempfile.TemporaryDirectory(prefix="clara-parsed-input-") as input_directory,
        _run_directory(request.output_dir.parent) as temporary_dir,
    ):
        run_dir = Path(temporary_dir)
        input_evidence = _portable_input_evidence(request.input_file)
        input_path = request.input_file
        parser_evidence: dict[str, Any] = {
            "status": "component_parser",
            "boundary": "No explicit parser contract supplied.",
        }
        if request.parser_settings is not None:
            input_path, parser_evidence = prepare_dataset_input(
                request.input_file, Path(input_directory), request.parser_settings
            )
        run_request = replace(request, output_dir=run_dir, input_file=input_path)
        recipe_path, run_recipe_audit = build_render_recipe(
            run_request,
            root=resolved_root,
        )
        _enforce_render_preflight(run_recipe_audit)
        request_evidence = _render_request_evidence(request)
        if adapter["component_name"] == "attribute-reporting":
            runner_result = _render_attribute_table(run_request, adapter)
            command: list[str] = []
        else:
            component_root = Path(str(adapter["component_root"]))
            command = _runner_command(
                run_request,
                component_root=component_root,
                recipe_path=recipe_path or run_request.recipe_path,
            )
            logs = request.output_dir / ".logs"
            logs.mkdir(exist_ok=True)
            stdout_path = logs / f"{run_dir.name}.stdout.log"
            stderr_path = logs / f"{run_dir.name}.stderr.log"
            with stdout_path.open("x") as stdout, stderr_path.open("x") as stderr:
                completed = run_process(
                    command,
                    cwd=component_root,
                    text=True,
                    stdout=stdout,
                    stderr=stderr,
                    check=False,
                    timeout=request.timeout_seconds,
                )
            with stdout_path.open() as stdout, stderr_path.open() as stderr:
                output_excerpt = stdout.read(65536)
                error_excerpt = stderr.read(65536)
            runner_result = {
                "status": "ok" if completed.returncode == 0 else "failed",
                "runner_type": "component_cli",
                "returncode": completed.returncode,
                "stdout": output_excerpt,
                "stderr": error_excerpt,
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "log_excerpt_limit": 65536,
            }

        if _portable_input_evidence(request.input_file) != input_evidence:
            raise ValueError("Reporting input changed while the component was running")
        run_artifacts = artifact_files(run_dir)
        if "render_manifest.json" in run_artifacts:
            raise ValueError(
                "Reporting component may not write reserved render_manifest.json"
            )
        recipe_relative = (
            recipe_path.resolve().relative_to(run_dir.resolve()).as_posix()
            if recipe_path is not None
            else None
        )
        current_run_artifacts = sorted(
            artifact for artifact in run_artifacts if artifact != recipe_relative
        )
        render_proof = capability_render_proof(
            request.capability_id,
            current_run_artifacts,
            artifact_mode=request.artifact_mode,
            include_variants=request.include_variants,
            role_bindings=request.role_bindings,
            root=resolved_root,
        )
        if runner_result.get("returncode") != 0 or render_proof.get("status") in {
            "missing_expected_render",
            "unexpected_rendered_artifacts",
        }:
            failure = _load_json(request.output_dir / "render_manifest.json")
            failure.update(
                {
                    "runner": runner_result,
                    "render_proof": render_proof,
                    "staging_directory": str(run_dir),
                    "evidence": {
                        "input": input_evidence,
                        "request": request_evidence,
                        "outputs": [],
                    },
                }
            )
            write_json_receipt(request.output_dir / "render_manifest.json", failure)
            raise RuntimeError(
                f"Reporting render failed for {request.capability_id}: "
                f"{render_proof.get('status')}; {runner_result.get('stderr', '')}"
            )
        protected_inputs = {request.input_file.resolve()}
        if request.recipe_path is not None:
            protected_inputs.add(request.recipe_path.resolve())
        if any(
            (request.output_dir / relative).resolve() in protected_inputs
            for relative in run_artifacts
        ):
            raise ValueError("Rendered artifact would overwrite a reporting input")
        _publish_run_artifacts(run_dir, request.output_dir, run_artifacts)
        recipe_audit, published_recipe_path = _published_recipe_audit(
            run_recipe_audit,
            run_dir=run_dir,
            output_dir=request.output_dir,
        )
        recipe_evidence = (
            _portable_input_evidence(published_recipe_path)
            if published_recipe_path is not None
            else {
                "kind": "none",
                "reason": "No external or generated recipe was required.",
            }
        )
        output_records = _output_evidence(
            request.output_dir,
            current_run_artifacts,
        )

    artifacts = artifact_files(request.output_dir)
    manifest = {
        "schema_version": "0.2",
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
        "evidence": {
            "input": input_evidence,
            "parsing": parser_evidence,
            "request": request_evidence,
            "recipe": recipe_evidence,
            "outputs": output_records,
            "output_set_sha256": _canonical_json_sha256(output_records),
        },
        "boundary": (
            "Unified Clara reporting-engine render call with exact input, request, "
            "recipe, and current-run output byte evidence. Semantic chart selection "
            "and interpretation are outside this layer."
        ),
    }
    write_json_receipt(request.output_dir / "render_manifest.json", manifest)
    manifest["artifacts"] = artifact_files(request.output_dir)
    write_json_receipt(request.output_dir / "render_manifest.json", manifest)
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
    parser.add_argument(
        "--parser-settings-json", help="Explicit sheet_name and/or csv_options JSON."
    )
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
        parser_settings=(
            _json_arg(args.parser_settings_json) if args.parser_settings_json else None
        ),
    )
    result = render_capability(request)
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
