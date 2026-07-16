from __future__ import annotations

import json
from pathlib import Path

from scripts.build_chart_selection_setup_audit import build_chart_selection_setup_audit


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _capability(capability_id: str) -> dict:
    return {
        "capability_id": capability_id,
        "family": "test",
        "visual_grammar": "test_chart",
        "selection_emphasis": "test_emphasis",
        "best_when": "Use for a tested setup.",
        "avoid_when": "Avoid outside the tested setup.",
        "period_semantics": {"role": "none"},
        "selection_contract": {
            "dataset_requirements": {
                "metrics": {
                    "source_metric_roles": [
                        {
                            "role": "metric",
                            "accepted_metric_classes": ["additive_value"],
                        }
                    ]
                },
                "dimensions": {
                    "required_roles": ["category"],
                    "role_requirements": {
                        "category": {
                            "role": "category",
                            "resolution_type": "direct_dimension",
                        }
                    },
                },
            }
        },
    }


def test_build_chart_selection_setup_audit_summarizes_gap_types(
    tmp_path: Path,
) -> None:
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "validation_issues": [],
            "capabilities": {
                "test.ready": _capability("test.ready"),
                "test.semantic": _capability("test.semantic"),
                "test.dataset": _capability("test.dataset"),
            },
        },
    )
    compatibility_path = _write_json(
        tmp_path / "compatibility.json",
        {
            "counts": {"mechanically_compatible": 1, "mechanically_incomplete": 2},
            "results": [
                {
                    "capability_id": "test.ready",
                    "status": "mechanically_compatible",
                    "issues": [],
                    "role_resolutions": [],
                },
                {
                    "capability_id": "test.semantic",
                    "status": "mechanically_incomplete",
                    "issues": ["requires_semantic_or_package_role"],
                    "role_resolutions": [],
                },
                {
                    "capability_id": "test.dataset",
                    "status": "mechanically_incomplete",
                    "issues": ["missing_schema_role"],
                    "role_resolutions": [],
                },
            ],
        },
    )

    payload = build_chart_selection_setup_audit(
        selection_manifest_path=manifest_path,
        compatibility_audit_paths={"test_dataset": compatibility_path},
        output_json_path=tmp_path / "setup.json",
        output_md_path=tmp_path / "setup.md",
        output_html_path=tmp_path / "setup.html",
    )

    assert payload["overall_status_counts"] == {
        "blocked_by_dataset_schema": 1,
        "blocked_by_semantic_or_package_layer": 1,
        "mechanically_ready_on_tested_profiles": 1,
    }
    assert payload["shortcoming_counts"] == {
        "dataset_schema_gap": 1,
        "semantic_or_package_gap": 1,
    }
    assert (tmp_path / "setup.json").exists()
    assert (tmp_path / "setup.md").exists()
    assert (tmp_path / "setup.html").exists()
