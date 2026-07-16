from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_chart_plugin_parameter_contract as audit_module


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _capability(
    capability_id: str,
    *,
    period_role: str,
    metric_roles: list[str],
    dimension_roles: list[str],
) -> dict:
    return {
        "capability_id": capability_id,
        "family": "test",
        "period_semantics": {"role": period_role},
        "metric_requirements": {
            "source_metric_roles": [
                {"role": role, "required": True} for role in metric_roles
            ]
        },
        "selection_contract": {
            "dataset_requirements": {
                "dimensions": {
                    "required_roles": dimension_roles,
                    "role_requirements": {
                        role: {"role": role, "required": True}
                        for role in dimension_roles
                    },
                }
            }
        },
    }


def _artifact(capability_id: str, recipe_href: str, *, panel: bool = False) -> dict:
    roles = ["panel_dimension"] if panel else []
    return {
        "label": capability_id,
        "capability_id": capability_id,
        "sidecars": [{"label": "recipe", "href": recipe_href}],
        "original_artifact_contract": {
            "required_parameters": [],
            "optional_parameters": [],
        },
        "rendering_variant": {"adds_parameter_roles": roles},
    }


def test_audit_chart_plugin_parameter_contract_maps_roles_and_variants(
    tmp_path: Path, monkeypatch
) -> None:
    gallery_dir = tmp_path / "gallery"
    monkeypatch.setattr(audit_module, "GALLERY_DIR", gallery_dir)
    _write_json(
        gallery_dir / "recipes" / "ready.json",
        {
            "mappings": {
                "period_column": "Date",
                "amount_column": "Sales",
                "related_marker_metric_column": "Units",
                "dot_dimension": "Brand",
                "small_multiples_dimension": "Channel",
            }
        },
    )
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "capabilities": {
                "test.ready": _capability(
                    "test.ready",
                    period_role="filter",
                    metric_roles=["primary_metric", "related_marker_metric"],
                    dimension_roles=["point_dimension"],
                )
            },
            "artifacts": [_artifact("test.ready", "recipes/ready.json", panel=True)],
        },
    )

    payload = audit_module.audit_chart_plugin_parameter_contract(
        selection_manifest_path=manifest_path,
        output_json_path=tmp_path / "audit.json",
        output_md_path=tmp_path / "audit.md",
    )

    assert payload["counts"]["parameter_contract_ready"] == 1
    assert payload["counts"]["parameter_contract_gap"] == 0
    result = payload["results"][0]
    assert result["status"] == "parameter_contract_ready"
    mapped_roles = {
        (mapping["kind"], mapping["role"])
        for mapping in result["role_mappings"] + result["variant_role_mappings"]
    }
    assert ("metric", "related_marker_metric") in mapped_roles
    assert ("variant", "panel_dimension") in mapped_roles
    contract = payload["normalized_invocation_contracts"]["test.ready"]
    assert contract["status"] == "parameter_contract_ready"
    assert contract["plugin_sources"] == []
    assert any(
        role_contract["role"] == "related_marker_metric"
        for role_contract in contract["required_role_contracts"]
    )
    assert payload["role_registry"]["counts"]["chart_roles_missing_mapping"] == 0
    assert (tmp_path / "audit.json").exists()
    assert (tmp_path / "audit.md").exists()


def test_audit_chart_plugin_parameter_contract_reports_missing_roles(
    tmp_path: Path, monkeypatch
) -> None:
    gallery_dir = tmp_path / "gallery"
    monkeypatch.setattr(audit_module, "GALLERY_DIR", gallery_dir)
    _write_json(gallery_dir / "recipes" / "gap.json", {"mappings": {}})
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "capabilities": {
                "test.gap": _capability(
                    "test.gap",
                    period_role="none",
                    metric_roles=["x_metric"],
                    dimension_roles=["parent_driver"],
                )
            },
            "artifacts": [_artifact("test.gap", "recipes/gap.json")],
        },
    )

    payload = audit_module.audit_chart_plugin_parameter_contract(
        selection_manifest_path=manifest_path,
        output_json_path=tmp_path / "audit.json",
        output_md_path=tmp_path / "audit.md",
    )

    assert payload["counts"]["parameter_contract_ready"] == 0
    assert payload["counts"]["parameter_contract_gap"] == 1
    assert payload["missing_role_counts"] == {"parent_driver": 1, "x_metric": 1}
    contract = payload["normalized_invocation_contracts"]["test.gap"]
    assert contract["status"] == "parameter_contract_gap"
    assert {missing["role"] for missing in contract["missing_roles"]} == {
        "parent_driver",
        "x_metric",
    }
