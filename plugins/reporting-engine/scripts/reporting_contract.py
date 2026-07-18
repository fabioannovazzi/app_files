"""Inspect the packaged Clara reporting-engine chart contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = [
    "catalog_root",
    "load_adapter_registry",
    "load_manifest",
    "load_manifest_summary",
    "load_semantic_layer_schema",
    "summarize_contract",
    "write_manifest_summary",
    "main",
]


def catalog_root() -> Path:
    """Return the packaged catalog directory."""

    return Path(__file__).resolve().parents[1] / "catalog"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_acceptance_digests_match(
    component_root: Path, acceptance: dict[str, Any]
) -> bool:
    inputs = acceptance.get("inputs") or {}
    records = [
        inputs.get("manifest") or {},
        inputs.get("semantic_schema") or {},
        inputs.get("dataset") or {},
        inputs.get("semantic_layer") or {},
        *(inputs.get("semantic_sources") or []),
    ]
    if not records:
        return False
    for record in records:
        relative_path = record.get("path")
        expected_digest = record.get("sha256")
        if not relative_path or not expected_digest:
            return False
        path = component_root / str(relative_path)
        if not path.is_file() or _sha256_file(path) != expected_digest:
            return False
    return True


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


def load_semantic_layer_schema(root: Path | None = None) -> dict[str, Any]:
    """Load the dataset-specific semantic-layer JSON Schema."""

    resolved_root = root or catalog_root()
    return _load_json(resolved_root / "semantic_layer.schema.json")


def summarize_contract(root: Path | None = None) -> dict[str, Any]:
    """Return a compact, stable reporting contract summary."""

    resolved_root = root or catalog_root()
    manifest = load_manifest(resolved_root)
    manifest_path = resolved_root / "selection_manifest.json"
    adapter_registry = load_adapter_registry(resolved_root)
    semantic_layer_schema = load_semantic_layer_schema(resolved_root)
    acceptance_path = resolved_root / "mechanical_acceptance_summary.json"
    acceptance = _load_json(acceptance_path) if acceptance_path.exists() else {}
    semantic_acceptance_path = resolved_root / "semantic_acceptance_summary.json"
    semantic_acceptance = (
        _load_json(semantic_acceptance_path)
        if semantic_acceptance_path.exists()
        else {}
    )
    adapters = adapter_registry.get("adapters") or {}
    capabilities = manifest.get("capabilities") or {}
    artifacts = manifest.get("artifacts") or []
    selector_audit = manifest.get("selector_audit") or {}
    pairwise = selector_audit.get("pairwise_ambiguity") or {}
    role_registry = manifest.get("role_registry") or {}
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
        "schema_version": "0.3",
        "manifest_schema_version": manifest.get("schema_version"),
        "capability_count": len(capabilities),
        "artifact_count": len(artifacts),
        "role_registry_count": len(role_registry.get("chart_roles") or {}),
        "profile_role_count": len(role_registry.get("profile_roles") or {}),
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
        "mechanical_acceptance": {
            "result": acceptance.get("result", "missing"),
            "selected_capability_count": acceptance.get("selected_capability_count", 0),
            "counts": acceptance.get("counts") or {},
            "manifest_digest_matches": (
                (acceptance.get("manifest") or {}).get("sha256")
                == _sha256_file(manifest_path)
            ),
        },
        "semantic_layer": {
            "schema_version": (
                (semantic_layer_schema.get("properties") or {})
                .get("schema_version", {})
                .get("const")
            ),
            "schema_id": semantic_layer_schema.get("$id"),
            "schema_sha256": _sha256_file(resolved_root / "semantic_layer.schema.json"),
            "workflow_script": "scripts/semantic_layer.py",
            "reviewed_fixture": (
                "fixtures/semantic_layer/retail_monthly.semantic.json"
            ),
            "judgment_owner": "model_or_human_review",
            "deterministic_scope": (
                "Scaffolding and contract validation only; semantic assertions "
                "remain source-backed model or human judgments."
            ),
            "acceptance": {
                "result": semantic_acceptance.get("result", "missing"),
                "semantic_layer_id": semantic_acceptance.get("semantic_layer_id"),
                "semantic_readiness": (
                    (semantic_acceptance.get("validation") or {}).get(
                        "semantic_readiness"
                    )
                ),
                "analysis_validities": (
                    (
                        (semantic_acceptance.get("validation") or {}).get("counts")
                        or {}
                    ).get("analysis_validities")
                    or {}
                ),
                "input_digests_match": _semantic_acceptance_digests_match(
                    resolved_root.parent, semantic_acceptance
                ),
            },
        },
        "boundary": (
            "Chart capability, mechanical parameter, dataset profile, and "
            "dataset-specific semantic-layer contracts. Clara owns the "
            "reporting-engine adapter registry; legacy plugin sources are "
            "provenance only. The component validates semantic wiring but does "
            "not author semantic truth or choose a final chart."
        ),
    }


def write_manifest_summary(root: Path | None = None) -> Path:
    """Regenerate the compact summary beside the canonical manifest."""

    resolved_root = root or catalog_root()
    output_path = resolved_root / "manifest_summary.json"
    output_path.write_text(
        json.dumps(summarize_contract(resolved_root), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return output_path


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
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Regenerate manifest_summary.json in the selected catalog.",
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
    if args.write_summary:
        print(write_manifest_summary(root))
        return 0
    print(json.dumps(summarize_contract(root), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
