from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_chart_selection_pairwise_ambiguity import (
    audit_chart_selection_pairwise_ambiguity,
)


def _write_manifest(path: Path, capabilities: dict) -> Path:
    path.write_text(json.dumps({"capabilities": capabilities}), encoding="utf-8")
    return path


def _capability(
    capability_id: str,
    *,
    emphasis: str,
    primary_cue: str,
    requires_focus: list[str],
    forbidden_focus: list[str],
    competitors: list[str] | None = None,
    negative_better_id: str | None = None,
    ambiguous_candidates: list[str] | None = None,
) -> dict:
    negative_questions = []
    if negative_better_id is not None:
        negative_questions.append(
            {
                "question": "Use the neighboring chart instead.",
                "why_not": f"This asks for `{negative_better_id}`, not `{emphasis}`.",
                "better_capability_id": negative_better_id,
            }
        )
    ambiguous_questions = []
    if ambiguous_candidates is not None:
        ambiguous_questions.append(
            {
                "question": "Show the broad chart family.",
                "candidate_capability_ids": ambiguous_candidates,
                "disambiguation_needed": "Clarify the intended emphasis.",
            }
        )
    return {
        "capability_id": capability_id,
        "family": "test",
        "analysis_task_ids": ["same_task"],
        "selection_emphasis": emphasis,
        "primary_decision_cue": primary_cue,
        "requires_question_focus": requires_focus,
        "forbidden_question_focus": forbidden_focus,
        "competing_capability_ids": competitors or [],
        "selection_examples": {
            "positive_questions": ["Positive example."],
            "negative_questions": negative_questions,
            "ambiguous_questions": ambiguous_questions,
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


def test_pairwise_ambiguity_audit_accepts_explicit_tie_breakers(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "selection_manifest.json",
        {
            "test.left": _capability(
                "test.left",
                emphasis="left_focus",
                primary_cue="Question asks for the left treatment.",
                requires_focus=["left_focus"],
                forbidden_focus=["right_focus"],
                competitors=["test.right"],
                negative_better_id="test.right",
                ambiguous_candidates=["test.left", "test.right"],
            ),
            "test.right": _capability(
                "test.right",
                emphasis="right_focus",
                primary_cue="Question asks for the right treatment.",
                requires_focus=["right_focus"],
                forbidden_focus=["left_focus"],
                competitors=["test.left"],
                ambiguous_candidates=["test.right", "test.left"],
            ),
        },
    )

    payload = audit_chart_selection_pairwise_ambiguity(
        selection_manifest_path=manifest_path,
        output_json_path=tmp_path / "audit.json",
        output_md_path=tmp_path / "audit.md",
    )

    assert payload["counts"]["high_overlap_pairs"] == 1
    assert payload["counts"]["unresolved_pairs"] == 0
    assert payload["counts"]["errors"] == 0
    assert payload["counts"]["warnings"] == 0
    assert payload["relationship_evidence_counts"] == {
        "ambiguous_example_link": 1,
        "explicit_competitor_link": 1,
        "negative_example_link": 1,
    }
    assert (tmp_path / "audit.json").exists()
    assert (tmp_path / "audit.md").exists()


def test_pairwise_ambiguity_audit_flags_missing_tie_breakers(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "selection_manifest.json",
        {
            "test.left": _capability(
                "test.left",
                emphasis="same_focus",
                primary_cue="Question asks for the same treatment.",
                requires_focus=["same_focus"],
                forbidden_focus=["other_focus"],
            ),
            "test.right": _capability(
                "test.right",
                emphasis="same_focus",
                primary_cue="Question asks for the same treatment.",
                requires_focus=["same_focus"],
                forbidden_focus=["other_focus"],
            ),
        },
    )

    payload = audit_chart_selection_pairwise_ambiguity(
        selection_manifest_path=manifest_path,
        output_json_path=tmp_path / "audit.json",
        output_md_path=tmp_path / "audit.md",
    )

    assert payload["counts"]["high_overlap_pairs"] == 1
    assert payload["counts"]["unresolved_pairs"] == 1
    assert payload["counts"]["errors"] == 5
    pair = payload["high_overlap_pairs"][0]
    issue_codes = {issue["code"] for issue in pair["issues"]}
    assert "same_selection_emphasis" in issue_codes
    assert "same_primary_decision_cue" in issue_codes
    assert "same_structured_decision_cues" in issue_codes
    assert "missing_explicit_competitor_link" in issue_codes
    assert "missing_ambiguous_example_link" in issue_codes
