from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_chart_selection_examples import audit_chart_selection_examples


def _write_manifest(path: Path, capabilities: dict) -> Path:
    path.write_text(json.dumps({"capabilities": capabilities}), encoding="utf-8")
    return path


def _capability(
    capability_id: str,
    *,
    focus: list[str],
    emphasis: str,
    positive: str,
    ambiguous: str = "How did sales change over time?",
    better_id: str = "test.other",
) -> dict:
    return {
        "capability_id": capability_id,
        "family": "test",
        "selection_emphasis": emphasis,
        "requires_question_focus": focus,
        "selection_examples": {
            "positive_questions": [positive],
            "negative_questions": [
                {
                    "question": "Give exact monthly AC/PY sales values and variances.",
                    "why_not": ("This asks for `exact_values`, not " f"`{emphasis}`."),
                    "better_capability_id": better_id,
                }
            ],
            "ambiguous_questions": [
                {
                    "question": ambiguous,
                    "candidate_capability_ids": [capability_id, better_id],
                    "disambiguation_needed": (
                        f"Clarify whether the intended focus is `{emphasis}`, "
                        "`exact_values`."
                    ),
                }
            ],
        },
    }


def _other_capability(*, better_id: str = "test.ready") -> dict:
    return {
        "capability_id": "test.other",
        "family": "test",
        "selection_emphasis": "exact_values",
        "requires_question_focus": ["exact_period_values", "period_table"],
        "selection_examples": {
            "positive_questions": [
                "Give exact monthly AC/PY sales values and variances."
            ],
            "negative_questions": [
                {
                    "question": "How did monthly cosmetics sales evolve versus previous year?",
                    "why_not": "This asks for `trajectory_shape`, not `exact_values`.",
                    "better_capability_id": better_id,
                }
            ],
            "ambiguous_questions": [
                {
                    "question": "Show period movement.",
                    "candidate_capability_ids": ["test.other", better_id],
                    "disambiguation_needed": (
                        "Clarify whether the intended focus is `exact_values`, "
                        "`trajectory_shape`."
                    ),
                }
            ],
        },
    }


def test_audit_chart_selection_examples_accepts_focused_examples(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "selection_manifest.json",
        {
            "test.ready": _capability(
                "test.ready",
                focus=["trajectory_shape", "current_vs_baseline_period_axis"],
                emphasis="trajectory_shape",
                positive="How did monthly cosmetics sales evolve versus previous year?",
            ),
            "test.other": _other_capability(),
        },
    )

    payload = audit_chart_selection_examples(
        selection_manifest_path=manifest_path,
        output_json_path=tmp_path / "audit.json",
        output_md_path=tmp_path / "audit.md",
    )

    assert payload["counts"]["failed"] == 0
    assert payload["counts"]["errors"] == 0
    assert (tmp_path / "audit.json").exists()
    assert (tmp_path / "audit.md").exists()


def test_audit_chart_selection_examples_flags_generic_positive_question(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "selection_manifest.json",
        {
            "test.generic": _capability(
                "test.generic",
                focus=["trajectory_shape", "current_vs_baseline_period_axis"],
                emphasis="trajectory_shape",
                positive="How did sales change over time?",
                ambiguous="How did sales change over time?",
            ),
            "test.other": _other_capability(better_id="test.generic"),
        },
    )

    payload = audit_chart_selection_examples(
        selection_manifest_path=manifest_path,
        output_json_path=tmp_path / "audit.json",
        output_md_path=tmp_path / "audit.md",
    )

    result = next(
        item for item in payload["results"] if item["capability_id"] == "test.generic"
    )
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert result["status"] == "fail"
    assert "positive_question_duplicates_ambiguous_prompt" in issue_codes
    assert "positive_question_missing_focus_evidence" in issue_codes
