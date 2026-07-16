from __future__ import annotations

import json
from pathlib import Path

from scripts.build_chart_manifest_practice_review import (
    build_chart_manifest_practice_review,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _capability(capability_id: str) -> dict:
    return {
        "capability_id": capability_id,
        "family": "test",
        "selection_emphasis": "ranked_single_metric_comparison",
        "primary_decision_cue": "Question asks to rank a dimension.",
        "requires_question_focus": ["single_metric_rank"],
        "reject_decision_cues": ["asks for time trend"],
        "best_when": "Use when ranking one metric.",
        "avoid_when": "Avoid for trajectories.",
        "selection_examples": {
            "positive_questions": ["Which category has the highest sales?"]
        },
        "selection_contract": {
            "dataset_requirements": {
                "period": {
                    "role": "filter",
                    "requires_period_axis": False,
                    "allows_period_filter": True,
                },
                "metrics": {
                    "source_metric_roles": [
                        {
                            "role": "primary_metric",
                            "accepted_metric_classes": ["additive_value"],
                        }
                    ],
                    "derived_metric_roles": [],
                    "display_metric_roles": ["primary_metric"],
                },
                "dimensions": {
                    "required_roles": ["dimension_member"],
                    "optional_roles": [],
                },
            }
        },
        "normalized_invocation_contract": {
            "status": "parameter_contract_ready",
            "plugin_sources": ["test-plugin"],
            "artifact_labels": ["test / bar"],
            "output_forms": ["chart_html"],
            "required_role_contracts": [
                {
                    "kind": "metric",
                    "role": "primary_metric",
                    "status": "mapped",
                    "mapping_kind": "explicit",
                    "parameter_targets": [
                        {
                            "target_type": "recipe_path",
                            "target": "mappings.amount_column",
                        }
                    ],
                }
            ],
            "variant_role_contracts": [],
            "missing_roles": [],
            "parameter_source_count": 1,
        },
    }


def test_build_chart_manifest_practice_review_writes_evidence_html(
    tmp_path: Path,
) -> None:
    capability_id = "test.bar"
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "role_registry": {
                "purpose": "Canonical role vocabulary.",
                "counts": {"chart_roles": 2, "profile_roles": 2},
                "chart_roles": ["primary_metric", "dimension_member"],
                "profile_roles": ["metric", "direct_dimension"],
            },
            "capabilities": {capability_id: _capability(capability_id)},
        },
    )
    compatibility_path = _write_json(
        tmp_path / "compatibility.json",
        {
            "results": [
                {
                    "capability_id": capability_id,
                    "status": "mechanically_compatible",
                    "issues": [],
                    "mechanical_role_matches": [
                        {
                            "kind": "metric",
                            "role": "primary_metric",
                            "fit_status": "satisfied",
                            "ambiguity_status": "unambiguous",
                            "candidate_count": 1,
                            "candidate_columns": ["sales"],
                        }
                    ],
                    "unmatched_required_roles": [],
                    "ambiguous_required_roles": [],
                    "rejected_column_evidence": [
                        {
                            "kind": "metric",
                            "role": "primary_metric",
                            "rejected_count": 1,
                            "samples": [
                                {
                                    "column": "sales_share",
                                    "reason": "metric_class_not_accepted",
                                    "source_role": "metric",
                                    "metric_class": "share",
                                }
                            ],
                        }
                    ],
                    "analysis_validity_status": "not_checked",
                }
            ]
        },
    )
    parameter_path = _write_json(
        tmp_path / "parameter.json",
        {
            "results": [
                {"capability_id": capability_id, "status": "parameter_contract_ready"}
            ]
        },
    )
    stress_path = _write_json(
        tmp_path / "stress.json",
        {
            "records": [
                {
                    "capability_id": capability_id,
                    "status": "works",
                    "proof": {
                        "question": "Which category has the highest sales?",
                        "plugin_chart": "test_bar",
                    },
                    "png_evidence": {
                        "status": "rendered_question_png",
                        "relative_path": "png/test_bar.png",
                        "renderer": "test renderer",
                    },
                }
            ]
        },
    )
    render_path = _write_json(
        tmp_path / "render.json",
        {
            "records": [
                {
                    "capability_id": capability_id,
                    "render_proof_status": "dataset_rendered_png_proven",
                    "fixture_requirement": "none",
                }
            ]
        },
    )
    family_path = _write_json(
        tmp_path / "family.json",
        {
            "families": [
                {
                    "family": "test",
                    "capability_ids": [capability_id],
                    "answers": {"positive_questions_specific": "Yes."},
                    "evidence": {},
                    "manual_focus_review": None,
                }
            ]
        },
    )
    gallery_path = _write_json(
        tmp_path / "gallery.json",
        {
            "items": [
                {
                    "label": "test / bar",
                    "plugin_source": "test-plugin",
                    "source": "test/source.html",
                    "output": "test.png",
                    "artifact_contract": {
                        "capability_id": capability_id,
                        "required_parameters": ["metric", "dimension"],
                        "optional_parameters": ["period"],
                        "outputs": [{"artifact_type": "png"}],
                    },
                }
            ]
        },
    )

    payload = build_chart_manifest_practice_review(
        selection_manifest_path=manifest_path,
        compatibility_audit_path=compatibility_path,
        parameter_audit_path=parameter_path,
        stress_test_path=stress_path,
        render_proof_matrix_path=render_path,
        family_review_path=family_path,
        gallery_manifest_path=gallery_path,
        output_json_path=tmp_path / "review.json",
        output_html_path=tmp_path / "review.html",
    )

    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert payload["counts"]["capabilities"] == 1
    assert payload["counts"]["practice_status"] == {"dataset_rendered_png_proven": 1}
    assert payload["remaining_work"]["needs_question_render_fixture"] == []
    assert "Role Registry" in html
    assert "Missing / Gaps" in html
    assert "Which category has the highest sales?" in html
    assert "mappings.amount_column" in html
    assert "sales_share" in html
    assert "metric_class_not_accepted" in html


def test_build_chart_manifest_practice_review_allows_public_image_prefixes(
    tmp_path: Path,
) -> None:
    capability_id = "test.bar"
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        {
            "role_registry": {
                "purpose": "Canonical role vocabulary.",
                "counts": {"chart_roles": 2, "profile_roles": 2},
                "chart_roles": ["primary_metric", "dimension_member"],
                "profile_roles": ["metric", "direct_dimension"],
            },
            "capabilities": {capability_id: _capability(capability_id)},
        },
    )
    compatibility_path = _write_json(
        tmp_path / "compatibility.json",
        {
            "results": [
                {
                    "capability_id": capability_id,
                    "status": "mechanically_compatible",
                    "issues": [],
                    "mechanical_role_matches": [],
                    "unmatched_required_roles": [],
                    "ambiguous_required_roles": [],
                    "rejected_column_evidence": [],
                }
            ]
        },
    )
    parameter_path = _write_json(
        tmp_path / "parameter.json",
        {
            "results": [
                {"capability_id": capability_id, "status": "parameter_contract_ready"}
            ]
        },
    )
    stress_path = _write_json(
        tmp_path / "stress.json",
        {
            "records": [
                {
                    "capability_id": capability_id,
                    "status": "works",
                    "proof": {
                        "question": "Which category has the highest sales?",
                        "plugin_chart": "test_bar",
                    },
                    "png_evidence": {
                        "status": "rendered_question_png",
                        "relative_path": "png/test_bar.png",
                    },
                }
            ]
        },
    )
    render_path = _write_json(
        tmp_path / "render.json",
        {
            "records": [
                {
                    "capability_id": capability_id,
                    "render_proof_status": "dataset_rendered_png_proven",
                    "fixture_requirement": "none",
                }
            ]
        },
    )
    family_path = _write_json(tmp_path / "family.json", {"families": []})
    gallery_path = _write_json(tmp_path / "gallery.json", {"items": []})

    payload = build_chart_manifest_practice_review(
        selection_manifest_path=manifest_path,
        compatibility_audit_path=compatibility_path,
        parameter_audit_path=parameter_path,
        stress_test_path=stress_path,
        render_proof_matrix_path=render_path,
        family_review_path=family_path,
        gallery_manifest_path=gallery_path,
        output_json_path=tmp_path / "review.json",
        output_html_path=tmp_path / "review.html",
        rendered_asset_href_prefix="cosmetics_question_png_assets/",
        gallery_href_prefix="../png-gallery/",
    )

    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert (
        payload["records"][0]["image"]["href"]
        == "cosmetics_question_png_assets/png/test_bar.png"
    )
    assert 'src="cosmetics_question_png_assets/png/test_bar.png"' in html
