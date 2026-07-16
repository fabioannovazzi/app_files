"""Render one reporting manifest capability through Clara reporting-engine."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


@dataclass(frozen=True)
class RenderRequest:
    """Concrete request for one Clara reporting-engine render."""

    capability_id: str
    input_file: Path
    output_dir: Path
    recipe_path: Path | None = None
    role_bindings: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    language: str = "en"
    currency: str | None = None
    artifact_mode: str = ARTIFACT_MODE_DATA_AND_RENDER
    include_variants: bool = False


CAPABILITY_CHART_OPTIONS: dict[str, list[str]] = {
    "distribution.boxplot": ["boxplot"],
    "distribution.ecdf": ["ecdf"],
    "distribution.histogram": ["histogram"],
    "distribution.kernel_density": ["kernel_density"],
    "distribution.stripplot": ["stripplot"],
    "mix.area": ["area_absolute", "area_share"],
    "mix.bar": ["bar"],
    "mix.barmekko": ["barmekko"],
    "mix.cohort_lost_stacked_column": ["cohort_lost_stacked_column"],
    "mix.cohort_since_stacked_column": ["cohort_since_stacked_column"],
    "mix.column": ["column_total"],
    "mix.column_overlay": ["column_total_with_overlay"],
    "mix.like_for_like_column": ["like_for_like_column_total"],
    "mix.like_for_like_stacked_column": ["like_for_like_stacked_column"],
    "mix.marimekko": ["marimekko"],
    "mix.multitier_bar": ["multitier_bar"],
    "mix.pareto": ["pareto"],
    "mix.stacked_bar": ["stacked_bar"],
    "mix.stacked_bar_overlay": ["related_metrics_bar"],
    "mix.stacked_column": ["stacked_column"],
    "mix.stacked_pareto": ["stacked_pareto"],
    "mix.timeline": ["line"],
    "period_comparison.by_period": ["year_over_year_by_period"],
    "period_comparison.dot": ["year_over_year_dot"],
    "period_comparison.horizontal_waterfall": ["year_over_year_waterfall"],
    "period_comparison.multitier_column": ["year_over_year_column"],
    "period_comparison.slope": ["year_over_year_slope"],
    "period_comparison.trend": ["year_over_year_line"],
    "scatter.bubble": ["bubble"],
    "scatter.scatter": ["scatter"],
    "set_overlap.upset": ["upset"],
    "set_overlap.upset_small_multiples": ["upset_small_multiples"],
    "set_overlap.venn": ["venn"],
}

VARIANT_CHART_OPTIONS: dict[str, list[str]] = {
    "mix.bar": ["bar_small_multiples"],
    "mix.barmekko": ["barmekko_small_multiples"],
    "mix.marimekko": ["marimekko_small_multiples"],
    "mix.multitier_bar": [
        "multitier_bar_dimension_panels",
        "multitier_bar_two_dimension",
    ],
    "mix.stacked_bar": ["stacked_bar_small_multiples"],
    "mix.stacked_bar_overlay": ["related_metrics_bar_small_multiples"],
    "mix.stacked_column": ["stacked_column_small_multiples"],
    "mix.timeline": ["line_small_multiples"],
    "period_comparison.by_period": ["year_over_year_by_period_small_multiples"],
    "period_comparison.dot": ["year_over_year_dot_small_multiples"],
    "period_comparison.horizontal_waterfall": [
        "year_over_year_waterfall_small_multiples"
    ],
    "period_comparison.multitier_column": ["year_over_year_column_small_multiples"],
    "period_comparison.slope": ["year_over_year_slope_small_multiples"],
    "period_comparison.trend": ["year_over_year_small_multiples"],
    "scatter.bubble": ["bubble_small_multiples"],
    "scatter.scatter": ["scatter_small_multiples"],
}

CAPABILITY_OPTION_OVERRIDES: dict[str, dict[str, Any]] = {
    "variance.exploded_variance_bridge": {
        "exploded_variance_bridge": True,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.price_volume_mix": {
        "pvm_decomposition_ladder": True,
        "exploded_variance_bridge": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.root_cause_component_bridge": {
        "exploded_variance_bridge": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": True,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.root_cause_exploded_bridge": {
        "exploded_variance_bridge": False,
        "root_cause_bridge": True,
        "root_cause_bridge_drilldown_rows": [1],
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.root_cause_total_bridge": {
        "exploded_variance_bridge": False,
        "root_cause_bridge": True,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.scenario_bridge": {
        "exploded_variance_bridge": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": True,
    },
    "variance.total_by_dimension_bridge": {
        "exploded_variance_bridge": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": True,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
}


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


def _target_value(binding: Any, target: str) -> Any:
    if isinstance(binding, dict):
        if target in binding:
            return binding[target]
        target_key = target.split(".")[-1]
        if target_key in binding:
            return binding[target_key]
        if "value" in binding:
            return binding["value"]
        return None
    return binding


def _apply_role_contracts(
    recipe: dict[str, Any],
    role_contracts: list[dict[str, Any]],
    role_bindings: dict[str, Any],
) -> dict[str, list[str]]:
    applied: dict[str, list[str]] = {}
    for contract in role_contracts:
        role = str(contract.get("role") or "")
        if not role:
            continue
        binding = _binding_for_role(role_bindings, role)
        if binding is None:
            continue
        for target in contract.get("parameter_targets") or []:
            target_path = str(target.get("target") or "")
            if not target_path or target_path == "package_dir":
                continue
            value = _target_value(binding, target_path)
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


def capability_chart_options(
    capability_id: str, *, include_variants: bool = False
) -> list[str]:
    """Return runner chart names for one manifest capability."""

    charts = list(CAPABILITY_CHART_OPTIONS.get(capability_id, []))
    if include_variants:
        charts = _append_unique(charts, VARIANT_CHART_OPTIONS.get(capability_id, []))
    return [str(chart) for chart in charts]


def capability_option_overrides(capability_id: str) -> dict[str, Any]:
    """Return runner option overrides for one capability."""

    return dict(CAPABILITY_OPTION_OVERRIDES.get(capability_id, {}))


def _capability_contract(
    capability_id: str, *, root: Path | None = None
) -> dict[str, Any]:
    manifest = load_manifest(root)
    capabilities = manifest.get("capabilities") or {}
    capability = capabilities.get(capability_id)
    if not isinstance(capability, dict):
        raise KeyError(f"Unknown capability: {capability_id}")
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
    recipe = dict(base_recipe)
    recipe.setdefault("schema_version", "1.0")
    recipe["source_file"] = str(request.input_file)
    recipe["language"] = request.language
    recipe.setdefault("mappings", {})
    recipe.setdefault("options", {})
    if request.currency:
        recipe["options"]["currency"] = request.currency
    charts = capability_chart_options(
        request.capability_id, include_variants=request.include_variants
    )
    if charts:
        recipe["options"]["charts"] = charts
        if request.include_variants:
            recipe["options"]["small_multiples"] = True
    for key, value in capability_option_overrides(request.capability_id).items():
        recipe["options"][key] = value
    for key, value in options.items():
        if "." in key:
            _deep_set(recipe, key, value)
        else:
            recipe["options"][key] = value
    contract = _capability_contract(request.capability_id, root=root)
    role_contracts = list(contract.get("required_role_contracts") or [])
    if request.include_variants:
        role_contracts += list(contract.get("variant_role_contracts") or [])
    applied_roles = _apply_role_contracts(
        recipe,
        role_contracts,
        role_bindings,
    )
    if request.recipe_path is None and not role_bindings and not options and not charts:
        return None, {"status": "not_written_no_recipe_overrides"}
    generated_recipe_path = request.output_dir / "render_request_recipe.json"
    _write_json(generated_recipe_path, recipe)
    return generated_recipe_path, {
        "status": "written",
        "path": str(generated_recipe_path),
        "charts": charts,
        "applied_roles": applied_roles,
        "option_overrides": capability_option_overrides(request.capability_id),
    }


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
    from modules.pdp.attribute_table_templates import (  # noqa: PLC0415
        build_attribute_tables_from_package,
    )

    manifest = build_attribute_tables_from_package(
        Path(package_dir),
        output_dir=request.output_dir,
        table_keys=[_attribute_table_key(request.capability_id)],
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


def render_capability(
    request: RenderRequest,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Render one capability through its Clara reporting adapter."""

    resolved_root = root or reporting_engine_root()
    request.output_dir.mkdir(parents=True, exist_ok=True)
    adapter = resolve_capability_adapter(request.capability_id, root=resolved_root)
    plan = prepare_invocation_plan(request.capability_id, root=resolved_root)
    recipe_path, recipe_audit = build_render_recipe(request, root=resolved_root)
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
        "artifacts": artifact_files(request.output_dir),
        "boundary": (
            "Unified Clara reporting-engine render call. Semantic chart selection "
            "is outside this layer."
        ),
    }
    _write_json(request.output_dir / "render_manifest.json", manifest)
    manifest["artifacts"] = artifact_files(request.output_dir)
    _write_json(request.output_dir / "render_manifest.json", manifest)
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
