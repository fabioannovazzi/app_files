from __future__ import annotations

import json
from pathlib import Path

from scripts.build_chart_render_proof_matrix import build_chart_render_proof_matrix


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_chart_render_proof_matrix_classifies_fixture_needs(
    tmp_path: Path,
) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        {
            "capabilities": {
                "test.rendered": {
                    "family": "test",
                    "selection_emphasis": "rendered",
                    "normalized_invocation_contract": {
                        "status": "parameter_contract_ready",
                        "artifact_labels": ["rendered"],
                        "output_forms": ["chart_png"],
                        "missing_roles": [],
                    },
                },
                "test.semantic": {
                    "family": "test",
                    "selection_emphasis": "semantic",
                    "normalized_invocation_contract": {
                        "status": "parameter_contract_ready",
                        "artifact_labels": ["semantic"],
                        "output_forms": ["table_png"],
                        "missing_roles": [],
                    },
                },
                "test.period_filter": {
                    "family": "test",
                    "selection_emphasis": "period_filter",
                    "period_scope_contract": {
                        "role": "filter",
                        "scope_required_for_render": True,
                        "explicit_all_data_allowed": True,
                        "accepted_scope_controls": ["options.selected_periods"],
                        "unscoped_default": "all_available_records",
                    },
                    "normalized_invocation_contract": {
                        "status": "parameter_contract_ready",
                        "artifact_labels": ["period-filter"],
                        "output_forms": ["chart_png"],
                        "missing_roles": [],
                    },
                },
            }
        },
    )
    parameter_path = _write_json(
        tmp_path / "parameter.json",
        {
            "results": [
                {
                    "capability_id": "test.rendered",
                    "status": "parameter_contract_ready",
                },
                {
                    "capability_id": "test.semantic",
                    "status": "parameter_contract_ready",
                },
                {
                    "capability_id": "test.period_filter",
                    "status": "parameter_contract_ready",
                },
            ]
        },
    )
    compatibility_path = _write_json(
        tmp_path / "compatibility.json",
        {
            "results": [
                {"capability_id": "test.rendered", "status": "mechanically_compatible"},
                {
                    "capability_id": "test.semantic",
                    "status": "mechanically_incomplete",
                    "issues": ["requires_semantic_or_package_role"],
                },
                {
                    "capability_id": "test.period_filter",
                    "status": "mechanically_compatible",
                    "issues": [],
                    "period_scope": {
                        "role": "filter",
                        "status": "caller_scope_required_before_render",
                        "scope_required_for_render": True,
                        "explicit_all_data_allowed": True,
                        "accepted_scope_controls": ["options.selected_periods"],
                        "period_candidates": ["date"],
                        "unscoped_default": "all_available_records",
                        "pre_render_warning": (
                            "This chart has a period filter. A caller must pass "
                            "a bounded analysis period or explicitly request all "
                            "available data."
                        ),
                    },
                },
            ]
        },
    )
    stress_path = _write_json(
        tmp_path / "stress.json",
        {
            "records": [
                {
                    "capability_id": "test.rendered",
                    "status": "works",
                    "png_evidence": {"status": "rendered_question_png"},
                },
                {
                    "capability_id": "test.semantic",
                    "status": "semantic_gap",
                    "png_evidence": {"status": "gallery_png"},
                },
                {
                    "capability_id": "test.period_filter",
                    "status": "dataset_gap",
                    "png_evidence": {"status": "missing"},
                },
            ]
        },
    )

    payload = build_chart_render_proof_matrix(
        selection_manifest_path=manifest_path,
        parameter_audit_path=parameter_path,
        compatibility_audit_path=compatibility_path,
        stress_test_path=stress_path,
        output_json_path=tmp_path / "matrix.json",
        output_md_path=tmp_path / "matrix.md",
    )

    records = {record["capability_id"]: record for record in payload["records"]}
    assert (
        records["test.rendered"]["render_proof_status"] == "dataset_rendered_png_proven"
    )
    assert records["test.rendered"]["fixture_requirement"] == "none"
    assert records["test.semantic"]["render_proof_status"] == "semantic_or_package_gap"
    assert (
        records["test.semantic"]["fixture_requirement"] == "semantic_or_package_fixture"
    )
    assert records["test.period_filter"]["period_scope_status"] == (
        "caller_scope_required_before_render"
    )
    assert records["test.period_filter"]["period_scope"]["period_candidates"] == [
        "date"
    ]
    assert (
        payload["counts"]["period_scope_status"]["caller_scope_required_before_render"]
        == 1
    )
    assert payload["counts"]["capabilities"] == 3
    assert (tmp_path / "matrix.json").exists()
    assert (tmp_path / "matrix.md").exists()
