from __future__ import annotations

import json
from pathlib import Path

from scripts.build_chart_selection_stress_test import build_chart_selection_stress_test


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _capability(capability_id: str) -> dict:
    return {
        "capability_id": capability_id,
        "family": "test",
        "visual_grammar": "test_chart",
        "analysis_task_ids": ["test_task"],
        "selection_emphasis": "test_emphasis",
        "best_when": "Use for a tested chart.",
        "avoid_when": "Avoid outside the tested case.",
        "axis_roles": {"x": "category", "y": "metric"},
        "period_semantics": {"role": "none"},
        "dimension_roles": ["category"],
        "dimension_contract": None,
        "competing_capability_ids": [],
        "example_artifact_labels": [],
        "metric_requirements": {
            "source_metric_roles": [],
            "derived_metric_roles": [],
            "minimum_source_metric_count": 0,
            "metric_selection_notes": [],
        },
        "selection_contract": {
            "dataset_requirements": {
                "metrics": {
                    "source_metric_roles": [],
                    "derived_metric_roles": [],
                    "minimum_source_metric_count": 0,
                    "display_metric_roles": [],
                    "metric_selection_notes": [],
                },
                "dimensions": {
                    "minimum_count": 1,
                    "required_roles": ["category"],
                    "optional_roles": [],
                    "dimension_contract": None,
                },
                "period": {
                    "role": "none",
                    "requires_period_axis": False,
                    "allows_period_filter": False,
                },
            }
        },
    }


def test_build_chart_selection_stress_test_classifies_core_statuses(
    tmp_path: Path,
) -> None:
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "capabilities": {
                "test.works": _capability("test.works"),
                "test.semantic": _capability("test.semantic"),
                "test.dataset": _capability("test.dataset"),
            }
        },
    )
    compatibility_path = _write_json(
        tmp_path / "compatibility.json",
        {
            "results": [
                {"capability_id": "test.works", "status": "mechanically_compatible"},
                {
                    "capability_id": "test.semantic",
                    "status": "mechanically_incomplete",
                    "issues": ["requires_semantic_or_package_role"],
                },
                {"capability_id": "test.dataset", "status": "mechanically_compatible"},
            ]
        },
    )
    proof_path = _write_json(
        tmp_path / "proof.json",
        {
            "results": [
                {
                    "capability_id": "test.works",
                    "verdict": "credible_data_artifact",
                    "question": "Can the tested chart answer the question?",
                    "plugin_chart": "test_chart",
                },
                {
                    "capability_id": "test.dataset",
                    "verdict": "correct_rejection",
                    "question": "Should this chart be rejected for the dataset?",
                    "plugin_chart": None,
                },
            ]
        },
    )
    gallery_path = _write_json(
        tmp_path / "gallery.json",
        {
            "items": [
                {
                    "output": "test.png",
                    "source": "../test/test.png",
                    "artifact_contract": {"capability_id": "test.semantic"},
                }
            ]
        },
    )
    assets_path = _write_json(
        tmp_path / "assets.json",
        {
            "outputs": [
                {
                    "capability_id": "test.works",
                    "status": "written",
                    "png_path": str(tmp_path / "test.png"),
                    "png_relative_path": "png/test.png",
                    "renderer": "test_renderer",
                }
            ]
        },
    )

    payload = build_chart_selection_stress_test(
        selection_manifest_path=manifest_path,
        compatibility_audit_path=compatibility_path,
        proof_path=proof_path,
        gallery_manifest_path=gallery_path,
        rendered_assets_path=assets_path,
        output_json_path=tmp_path / "stress.json",
        output_md_path=tmp_path / "stress.md",
        output_html_path=tmp_path / "stress.html",
    )

    assert payload["counts"] == {"dataset_gap": 1, "semantic_gap": 1, "works": 1}
    assert (tmp_path / "stress.json").exists()
    assert (tmp_path / "stress.md").exists()
    assert (tmp_path / "stress.html").exists()
