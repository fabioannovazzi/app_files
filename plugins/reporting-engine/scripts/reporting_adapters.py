"""Resolve Clara reporting-engine adapters for chart capabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

__all__ = [
    "adapter_registry_path",
    "catalog_root",
    "component_root",
    "list_adapters",
    "load_adapter_registry",
    "load_manifest",
    "prepare_invocation_plan",
    "reporting_engine_root",
    "resolve_capability_adapter",
    "summarize_adapters",
    "main",
]


def reporting_engine_root() -> Path:
    """Return the editable or packaged reporting-engine component root."""

    return Path(__file__).resolve().parents[1]


def catalog_root(root: Path | None = None) -> Path:
    """Return the reporting-engine catalog directory."""

    return (root or reporting_engine_root()) / "catalog"


def adapter_registry_path(root: Path | None = None) -> Path:
    """Return the adapter registry path."""

    return catalog_root(root) / "adapter_registry.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_adapter_registry(root: Path | None = None) -> dict[str, Any]:
    """Load the Clara reporting adapter registry."""

    return _load_json(adapter_registry_path(root))


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    """Load the chart-selection manifest."""

    return _load_json(catalog_root(root) / "selection_manifest.json")


def component_root(component_name: str, root: Path | None = None) -> Path:
    """Return the embedded Clara component root or repository fallback root."""

    base = root or reporting_engine_root()
    sibling = base.parent / component_name
    if sibling.is_dir():
        return sibling
    return sibling


def list_adapters(root: Path | None = None) -> list[dict[str, Any]]:
    """Return adapter records sorted by adapter id."""

    registry = load_adapter_registry(root)
    adapters = registry.get("adapters") or {}
    return sorted(
        (dict(adapter) for adapter in adapters.values()),
        key=lambda adapter: str(adapter.get("adapter_id") or ""),
    )


def _adapter_for_legacy_source(
    legacy_source: str, registry: dict[str, Any]
) -> dict[str, Any]:
    adapters = registry.get("adapters") or {}
    adapter = adapters.get(legacy_source)
    if not isinstance(adapter, dict):
        raise KeyError(f"No reporting-engine adapter registered for {legacy_source}")
    return adapter


def _capability_record(capability_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    capabilities = manifest.get("capabilities") or {}
    capability = capabilities.get(capability_id)
    if not isinstance(capability, dict):
        raise KeyError(f"Unknown capability: {capability_id}")
    return capability


def _legacy_source_for_capability(capability: dict[str, Any]) -> str:
    contract = capability.get("normalized_invocation_contract") or {}
    plugin_sources = contract.get("plugin_sources") or []
    if len(plugin_sources) != 1:
        raise ValueError(
            "Capability must have exactly one legacy plugin source to resolve "
            f"a reporting adapter: {plugin_sources}"
        )
    return str(plugin_sources[0])


def resolve_capability_adapter(
    capability_id: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Return the Clara adapter record for one manifest capability."""

    registry = load_adapter_registry(root)
    manifest = load_manifest(root)
    capability = _capability_record(capability_id, manifest)
    legacy_source = _legacy_source_for_capability(capability)
    adapter = dict(_adapter_for_legacy_source(legacy_source, registry))
    contract = capability.get("normalized_invocation_contract") or {}
    manifest_adapter = contract.get("clara_adapter") or {}
    resolved_root = component_root(str(adapter["component_name"]), root)
    adapter.update(
        {
            "capability_id": capability_id,
            "component_root": str(resolved_root),
            "component_exists": resolved_root.is_dir(),
            "manifest_adapter_id": manifest_adapter.get("adapter_id"),
            "manifest_adapter_matches_registry": (
                manifest_adapter.get("adapter_id") == adapter.get("adapter_id")
            ),
        }
    )
    return adapter


def _dataset_candidates_for_role(
    dataset_profile: dict[str, Any] | None,
    role_contract: dict[str, Any],
) -> list[str]:
    if not dataset_profile:
        return []
    role_candidates = dataset_profile.get("role_candidates") or {}
    role = str(role_contract.get("role") or "")
    if role in role_candidates:
        return [str(item) for item in role_candidates.get(role) or []]
    kind = str(role_contract.get("kind") or "")
    fallback_roles = {
        "period": "period_axis",
        "metric": "comparison_metric",
        "dimension": "dimension_member",
        "identifier": "identifier",
    }
    fallback = fallback_roles.get(kind)
    if fallback is None:
        return []
    return [str(item) for item in role_candidates.get(fallback) or []]


def _role_plan(
    contracts: list[dict[str, Any]],
    dataset_profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for contract in contracts:
        candidates = _dataset_candidates_for_role(dataset_profile, contract)
        plan.append(
            {
                "kind": contract.get("kind"),
                "role": contract.get("role"),
                "mapping_kind": contract.get("mapping_kind"),
                "status": contract.get("status"),
                "parameter_targets": contract.get("parameter_targets") or [],
                "dataset_candidates": candidates,
                "dataset_match_status": (
                    "not_checked"
                    if dataset_profile is None
                    else "candidate_available" if candidates else "missing_candidate"
                ),
            }
        )
    return plan


def prepare_invocation_plan(
    capability_id: str,
    *,
    dataset_profile: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Return a mechanical plan for rendering one chosen capability."""

    manifest = load_manifest(root)
    capability = _capability_record(capability_id, manifest)
    contract = capability.get("normalized_invocation_contract") or {}
    adapter = resolve_capability_adapter(capability_id, root=root)
    required_contracts = contract.get("required_role_contracts") or []
    variant_contracts = contract.get("variant_role_contracts") or []
    return {
        "schema_version": "0.1",
        "capability_id": capability_id,
        "owner": "clara.reporting-engine",
        "adapter_id": adapter.get("adapter_id"),
        "component_name": adapter.get("component_name"),
        "component_root": adapter.get("component_root"),
        "component_exists": adapter.get("component_exists"),
        "legacy_plugin_source": adapter.get("legacy_plugin_source"),
        "legacy_plugin_source_policy": (
            "Provenance only; Clara callers should invoke the reporting-engine "
            "adapter contract."
        ),
        "render_api_status": adapter.get("render_api_status"),
        "entrypoints": adapter.get("entrypoints") or {},
        "required_roles": _role_plan(required_contracts, dataset_profile),
        "variant_roles": _role_plan(variant_contracts, dataset_profile),
        "artifact_invocation_contracts": (
            contract.get("artifact_invocation_contracts") or []
        ),
        "output_forms": contract.get("output_forms") or [],
        "dataset_checked": dataset_profile is not None,
        "mechanical_status": contract.get("status"),
        "boundary": (
            "Mechanical adapter and parameter plan only. It does not choose a "
            "semantically valid analysis."
        ),
    }


def summarize_adapters(root: Path | None = None) -> dict[str, Any]:
    """Return a compact adapter registry summary."""

    registry = load_adapter_registry(root)
    manifest = load_manifest(root)
    adapters = registry.get("adapters") or {}
    capability_counts: dict[str, int] = {source: 0 for source in adapters}
    missing_sources: set[str] = set()
    for capability in (manifest.get("capabilities") or {}).values():
        if not isinstance(capability, dict):
            continue
        source = _legacy_source_for_capability(capability)
        if source in capability_counts:
            capability_counts[source] += 1
        else:
            missing_sources.add(source)
    return {
        "schema_version": "0.1",
        "owner": registry.get("owner"),
        "adapter_count": len(adapters),
        "adapter_ids": sorted(
            str(adapter.get("adapter_id")) for adapter in adapters.values()
        ),
        "component_names": sorted(
            str(adapter.get("component_name")) for adapter in adapters.values()
        ),
        "capability_counts_by_legacy_source": dict(sorted(capability_counts.items())),
        "missing_registry_sources": sorted(missing_sources),
        "legacy_plugin_source_policy": registry.get("legacy_plugin_source_policy"),
    }


def main(argv: list[str] | None = None) -> int:
    """Print the adapter summary or a resolved capability plan."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override catalog directory or reporting-engine root.",
    )
    parser.add_argument("--capability", help="Capability id to resolve.")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the invocation plan instead of only the adapter record.",
    )
    args = parser.parse_args(argv)
    root = None
    if args.catalog_root is not None:
        root = (
            args.catalog_root.parent
            if args.catalog_root.name == "catalog"
            else args.catalog_root
        )
    if args.capability:
        payload = (
            prepare_invocation_plan(args.capability, root=root)
            if args.plan
            else resolve_capability_adapter(args.capability, root=root)
        )
    else:
        payload = summarize_adapters(root)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
