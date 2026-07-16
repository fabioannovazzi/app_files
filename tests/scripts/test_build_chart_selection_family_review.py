from __future__ import annotations

import json
from pathlib import Path

from scripts.build_chart_selection_family_review import (
    REVIEW_QUESTIONS,
    build_chart_selection_family_review,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_chart_selection_family_review_answers_all_questions(
    tmp_path: Path,
) -> None:
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "capabilities": {
                "distribution.histogram": {
                    "family": "distribution",
                    "competing_capability_ids": [],
                }
            }
        },
    )
    example_path = _write_json(
        tmp_path / "selection_example_quality_audit.json",
        {
            "results": [
                {
                    "capability_id": "distribution.histogram",
                    "error_count": 0,
                    "warning_count": 0,
                }
            ]
        },
    )
    parameter_path = _write_json(
        tmp_path / "plugin_parameter_contract_audit.json",
        {
            "results": [
                {
                    "capability_id": "distribution.histogram",
                    "status": "parameter_contract_ready",
                }
            ]
        },
    )
    pairwise_path = _write_json(
        tmp_path / "pairwise_ambiguity_audit.json",
        {"high_overlap_pairs": []},
    )
    stress_path = _write_json(
        tmp_path / "chart_selection_stress_test.json",
        {
            "records": [
                {
                    "capability_id": "distribution.histogram",
                    "status": "works",
                }
            ]
        },
    )

    payload = build_chart_selection_family_review(
        selection_manifest_path=manifest_path,
        example_audit_path=example_path,
        pairwise_audit_path=pairwise_path,
        parameter_audit_path=parameter_path,
        stress_test_path=stress_path,
        output_json_path=tmp_path / "review.json",
        output_md_path=tmp_path / "review.md",
    )

    assert payload["counts"]["families"] == 1
    assert payload["counts"]["capabilities"] == 1
    assert payload["counts"]["example_errors"] == 0
    assert payload["counts"]["parameter_contract_gaps"] == 0
    assert payload["counts"]["manual_focus_review_families"] == 1
    assert set(payload["families"][0]["answers"]) == set(REVIEW_QUESTIONS)
    assert payload["families"][0]["manual_focus_review"]["review_status"] == "complete"
    review_text = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "Are positive questions specific?" in review_text
    assert "Are close competitors correctly listed?" in review_text
    assert "Does PNG/question review output match the stated purpose?" in review_text
    assert "Manual focus review" in review_text
