from __future__ import annotations

import json
from pathlib import Path

from scripts.build_chart_selection_family_playbooks import (
    build_chart_selection_family_playbooks,
)


def _write_manifest(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _capability(
    capability_id: str,
    *,
    family: str,
    emphasis: str,
    competitor_id: str,
) -> dict:
    return {
        "capability_id": capability_id,
        "family": family,
        "visual_grammar": "test_grammar",
        "analysis_task_ids": ["test_task"],
        "selection_emphasis": emphasis,
        "best_when": f"Use when the question asks for {emphasis}.",
        "avoid_when": f"Avoid when the question rejects {emphasis}.",
        "primary_decision_cue": f"Question asks for {emphasis}.",
        "requires_question_focus": [emphasis],
        "reject_decision_cues": [f"reject_{emphasis}"],
        "forbidden_question_focus": [f"not_{emphasis}"],
        "competing_capability_ids": [competitor_id],
        "selection_examples": {
            "positive_questions": [f"Show {emphasis}."],
            "negative_questions": [
                {
                    "question": f"Show {competitor_id}.",
                    "why_not": f"This asks for `{competitor_id}`, not `{emphasis}`.",
                    "better_capability_id": competitor_id,
                }
            ],
            "ambiguous_questions": [
                {
                    "question": "Show the broad family.",
                    "candidate_capability_ids": [capability_id, competitor_id],
                    "disambiguation_needed": "Clarify the intended emphasis.",
                }
            ],
        },
        "selection_contract": {
            "dataset_requirements": {
                "period": {"role": "axis"},
                "metrics": {
                    "minimum_source_metric_count": 1,
                    "source_metric_roles": [
                        {
                            "role": "primary_metric",
                            "required": True,
                            "accepted_metric_classes": ["additive_value"],
                        }
                    ],
                },
                "dimensions": {
                    "minimum_count": 1,
                    "required_roles": ["category"],
                    "optional_roles": ["panel_dimension"],
                    "role_requirements": {
                        "category": {"resolution_type": "direct_dimension"}
                    },
                },
            }
        },
    }


def test_build_chart_selection_family_playbooks_writes_review_files(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "selection_manifest.json",
        {
            "capabilities": {
                "test.left": _capability(
                    "test.left",
                    family="test_family",
                    emphasis="left_focus",
                    competitor_id="test.right",
                ),
                "test.right": _capability(
                    "test.right",
                    family="test_family",
                    emphasis="right_focus",
                    competitor_id="test.left",
                ),
            },
            "selector_audit": {
                "pairwise_ambiguity": {
                    "high_overlap_pairs": [
                        {
                            "capability_ids": ["test.left", "test.right"],
                            "status": "resolved",
                            "error_count": 0,
                            "warning_count": 0,
                            "relationship_evidence": {
                                "explicit_competitor_link": True,
                                "ambiguous_example_link": True,
                                "negative_example_link": True,
                            },
                        }
                    ]
                }
            },
        },
    )

    payload = build_chart_selection_family_playbooks(
        selection_manifest_path=manifest_path,
        output_dir=tmp_path / "playbooks",
    )

    assert payload["family_count"] == 1
    assert payload["capability_count"] == 2
    index_text = (tmp_path / "playbooks" / "index.md").read_text(encoding="utf-8")
    family_text = (tmp_path / "playbooks" / "test_family.md").read_text(
        encoding="utf-8"
    )
    assert "`test_family`" in index_text
    assert "`test.left`" in family_text
    assert "`left_focus`" in family_text
    assert "`not_left_focus`" in family_text
    assert "`primary_metric`" in family_text
    assert "required `category`; optional `panel_dimension`" in family_text
    assert "`test.right`: `resolved`" in family_text
    assert "`explicit_competitor_link`" in family_text
    assert "Show left_focus." in family_text
