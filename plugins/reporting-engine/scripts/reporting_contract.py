"""Inspect the packaged Clara reporting-engine chart contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

__all__ = [
    "catalog_root",
    "load_adapter_registry",
    "load_manifest",
    "load_manifest_summary",
    "summarize_contract",
    "main",
]


def catalog_root() -> Path:
    """Return the packaged catalog directory."""

    return Path(__file__).resolve().parents[1] / "catalog"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    """Load the chart-selection manifest."""

    resolved_root = root or catalog_root()
    return _load_json(resolved_root / "selection_manifest.json")


def load_manifest_summary(root: Path | None = None) -> dict[str, Any]:
    """Load the small manifest summary."""

    resolved_root = root or catalog_root()
    return _load_json(resolved_root / "manifest_summary.json")


def load_adapter_registry(root: Path | None = None) -> dict[str, Any]:
    """Load the Clara reporting adapter registry."""

    resolved_root = root or catalog_root()
    return _load_json(resolved_root / "adapter_registry.json")


def summarize_contract(root: Path | None = None) -> dict[str, Any]:
    """Return a compact, stable reporting contract summary."""

    resolved_root = root or catalog_root()
    manifest = load_manifest(resolved_root)
    adapter_registry = load_adapter_registry(resolved_root)
    adapters = adapter_registry.get("adapters") or {}
    capabilities = manifest.get("capabilities") or {}
    artifacts = manifest.get("artifacts") or []
    selector_audit = manifest.get("selector_audit") or {}
    pairwise = selector_audit.get("pairwise_ambiguity") or {}
    plugin_sources: set[str] = set()
    adapter_ids: set[str] = set()
    component_names: set[str] = set()
    render_api_statuses: dict[str, int] = {}
    invocation_statuses: dict[str, int] = {}
    for capability in capabilities.values():
        if not isinstance(capability, dict):
            continue
        contract = capability.get("normalized_invocation_contract") or {}
        status = str(contract.get("status") or "unknown")
        invocation_statuses[status] = invocation_statuses.get(status, 0) + 1
        for source in contract.get("plugin_sources") or []:
            legacy_source = str(source)
            plugin_sources.add(legacy_source)
            adapter = adapters.get(legacy_source) or {}
            if adapter:
                adapter_ids.add(str(adapter.get("adapter_id")))
                component_names.add(str(adapter.get("component_name")))
                render_status = str(adapter.get("render_api_status") or "unknown")
                render_api_statuses[render_status] = (
                    render_api_statuses.get(render_status, 0) + 1
                )
    return {
        "schema_version": "0.1",
        "manifest_schema_version": manifest.get("schema_version"),
        "capability_count": len(capabilities),
        "artifact_count": len(artifacts),
        "role_registry_count": len(manifest.get("role_registry") or {}),
        "plugin_sources": sorted(plugin_sources),
        "legacy_plugin_sources": sorted(plugin_sources),
        "clara_adapter_ids": sorted(adapter_ids),
        "clara_component_names": sorted(component_names),
        "adapter_registry": {
            "schema_version": adapter_registry.get("schema_version"),
            "owner": adapter_registry.get("owner"),
            "adapter_count": len(adapters),
            "legacy_plugin_source_policy": adapter_registry.get(
                "legacy_plugin_source_policy"
            ),
            "render_api_statuses": dict(sorted(render_api_statuses.items())),
        },
        "invocation_statuses": dict(sorted(invocation_statuses.items())),
        "coverage_gaps": manifest.get("coverage_gaps") or {},
        "selector_audit": {
            "result": selector_audit.get("result"),
            "capabilities_checked": selector_audit.get("capabilities_checked"),
            "duplicate_selector_signatures": len(
                selector_audit.get("duplicate_selector_signatures") or []
            ),
            "high_overlap_pair_count": pairwise.get("high_overlap_pair_count"),
            "unresolved_pair_count": pairwise.get("unresolved_pair_count"),
            "generated_manifest_only_capabilities": len(
                selector_audit.get("generated_manifest_only_capabilities") or []
            ),
        },
        "boundary": (
            "Non-semantic chart capability and mechanical parameter contract. "
            "Clara owns the reporting-engine adapter registry; legacy plugin "
            "sources are provenance only. This does not choose semantically "
            "valid analyses."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Print contract summary or one capability record."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override catalog directory.",
    )
    parser.add_argument(
        "--capability",
        help="Capability id to print instead of the summary.",
    )
    args = parser.parse_args(argv)
    root = args.catalog_root or catalog_root()
    if args.capability:
        manifest = load_manifest(root)
        capability = (manifest.get("capabilities") or {}).get(args.capability)
        if capability is None:
            raise SystemExit(f"Unknown capability: {args.capability}")
        print(json.dumps(capability, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(summarize_contract(root), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
