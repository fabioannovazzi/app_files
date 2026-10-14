"""Verify version-bound retained evidence and answer-bound human assessments."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from tests.plugins.test_deep_research_validator_plugin import load_script


@pytest.fixture
def evaluation():
    return load_script("legal_tax_evaluation_test", "research_evaluation.py")


def _spec(root: Path, workflow="standard_codex", identifier="evaluation-1"):
    root.mkdir(exist_ok=True)
    roles = {
        "assignment": "Describe the supplied fictional condition.",
        "material": "The fictional entitlement requires condition X.",
        "final_answer": "Entitlement remains conditional on X.",
        "execution_evidence": "Actual unit-test invocation; no model research run is claimed.",
    }
    config = {
        "host": "test-host",
        "model": "test-model",
        "research_date": "2026-10-13",
        "research_tools": ["supplied_files"],
        "configuration_observation": "Synthetic metadata for storage regression only.",
        "specialist_plugins_exposed": [],
    }
    if workflow != "standard_codex":
        product = workflow if workflow != "previous_pipeline" else "vera"
        roles.update(
            research_history="Supplied-condition review.",
            final_review="Synthetic reviewed answer.",
        )
        package = root / "plugin.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                ".claude-plugin/plugin.json",
                json.dumps({"name": product, "version": "0.1.1"}),
            )
        config["observed_plugin_version"] = "0.1.1"
    artifacts = []
    for role, content in roles.items():
        path = root / f"{role}.md"
        path.write_text(content, encoding="utf-8")
        artifacts.append({"role": role, "path": path.name})
    config_path = root / "host.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    artifacts.append({"role": "host_configuration", "path": config_path.name})
    if workflow != "standard_codex":
        artifacts.append({"role": "plugin_package", "path": "plugin.zip"})
        (root / "source_inventory.json").write_text(json.dumps({"sources": []}))
        artifacts.append({"role": "source_inventory", "path": "source_inventory.json"})
    return {
        "case_id": "fictional-condition",
        "evaluation_id": identifier,
        "workflow": workflow,
        "evaluation_kind": "fixed_source_reasoning",
        "trace_limits": [
            "This fixture is not a professional or model-quality evaluation."
        ],
        "artifacts": artifacts,
    }


@pytest.mark.parametrize(
    "workflow", ["standard_codex", "vera", "lucia", "previous_pipeline"]
)
def test_retention_preserves_actual_bytes_and_never_certifies_quality(
    tmp_path, evaluation, workflow
):
    spec = _spec(tmp_path, workflow)

    run = evaluation.record_evaluation(tmp_path, spec)
    record = evaluation.verify_evaluation(run)

    assert record["quality"] == "not_assessed_by_helper"
    assert record["assessment_status"] == "pending"
    assert record["execution_authenticity"] == "not_certified_by_file_hashes"
    assert record["host_configuration"]["model"] == "test-model"
    answer = next(
        item for item in record["artifacts"] if item["role"] == "final_answer"
    )
    assert (run / answer["path"]).read_bytes() == (
        tmp_path / "final_answer.md"
    ).read_bytes()
    if workflow != "standard_codex":
        assert record["product"]["version"] == "0.1.1"
        assert (
            record["product"]["package_sha256"]
            == hashlib.sha256((tmp_path / "plugin.zip").read_bytes()).hexdigest()
        )


@pytest.mark.parametrize(
    "role", ["assignment", "final_answer", "execution_evidence", "host_configuration"]
)
def test_missing_actual_evidence_is_rejected_before_retention(
    tmp_path, evaluation, role
):
    spec = _spec(tmp_path)
    spec["artifacts"] = [item for item in spec["artifacts"] if item["role"] != role]

    with pytest.raises(ValueError):
        evaluation.record_evaluation(tmp_path, spec)

    assert not (tmp_path / "evaluation_runs").exists()


def test_host_version_mismatch_cannot_be_labelled_as_new_plugin(tmp_path, evaluation):
    spec = _spec(tmp_path, "vera")
    config = json.loads((tmp_path / "host.json").read_text())
    config["observed_plugin_version"] = "0.0.9"
    (tmp_path / "host.json").write_text(json.dumps(config))

    with pytest.raises(ValueError, match="host version differs"):
        evaluation.record_evaluation(tmp_path, spec)

    assert not (tmp_path / "evaluation_runs").exists()


def test_changed_retained_answer_or_metadata_is_rejected(tmp_path, evaluation):
    run = evaluation.record_evaluation(tmp_path, _spec(tmp_path))
    record = evaluation.verify_evaluation(run)
    record["workflow"] = "vera"
    (run / "evaluation_record.json").write_text(json.dumps(record))

    with pytest.raises(ValueError, match="metadata changed"):
        evaluation.verify_evaluation(run)


def _assessment(record):
    answer = next(
        item for item in record["artifacts"] if item["role"] == "final_answer"
    )
    return {
        "final_answer_sha256": answer["sha256"],
        "reviewer": "Synthetic test rater",
        "reviewer_role": "test fixture",
        "assessment": "Storage-contract check; no legal-quality judgment.",
        "workflow_label_known": False,
    }


def test_assessment_is_bound_to_answer_and_preserves_original_run_record(
    tmp_path, evaluation
):
    run = evaluation.record_evaluation(tmp_path, _spec(tmp_path))
    before = (run / "evaluation_record.json").read_bytes()
    assessment = _assessment(evaluation.verify_evaluation(run))

    evaluation.record_assessment(run, assessment)

    record = evaluation.verify_evaluation(run)
    assert record["assessment_status"] == "recorded"
    assert record["quality"] == "not_assessed_by_helper"
    assert (run / "evaluation_record.json").read_bytes() == before
    with pytest.raises(ValueError, match="cannot be silently overwritten"):
        evaluation.record_assessment(run, assessment)


def test_wrong_answer_assessment_is_rejected_without_writing(tmp_path, evaluation):
    run = evaluation.record_evaluation(tmp_path, _spec(tmp_path))
    assessment = _assessment(evaluation.verify_evaluation(run))
    assessment["final_answer_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="different answer revision"):
        evaluation.record_assessment(run, assessment)

    assert not (run / "assessment.json").exists()


def test_blinded_bundle_withholds_workflow_mapping_and_preserves_delivered_content(
    tmp_path, evaluation
):
    baseline_root = tmp_path / "baseline"
    plugin_root = tmp_path / "specialist"
    baseline = evaluation.record_evaluation(
        baseline_root, _spec(baseline_root, identifier="baseline")
    )
    specialist = evaluation.record_evaluation(
        plugin_root, _spec(plugin_root, "vera", "specialist")
    )

    assessor = evaluation.export_blinded_comparison(
        [baseline, specialist], tmp_path / "comparison"
    )

    assert not (assessor / "private_mapping.json").exists()
    mapping = json.loads((assessor.parent / "private_mapping.json").read_text())
    assert {item["workflow"] for item in mapping["mapping"]} == {
        "standard_codex",
        "vera",
    }
    answers = list(assessor.rglob("*-final_answer.md"))
    assert len(answers) == 2
    assert {path.read_bytes() for path in answers} == {
        (baseline_root / "final_answer.md").read_bytes()
    }
    assert not list(assessor.rglob("*host_configuration*"))
    assert not list(assessor.rglob("*plugin_package*"))


def test_comparison_rejects_different_materials_before_export(tmp_path, evaluation):
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first = evaluation.record_evaluation(
        first_root, _spec(first_root, identifier="first")
    )
    spec = _spec(second_root, identifier="second")
    (second_root / "material.md").write_text("A different fictional condition.")
    second = evaluation.record_evaluation(second_root, spec)

    with pytest.raises(ValueError, match="same assignment, materials"):
        evaluation.export_blinded_comparison([first, second], tmp_path / "comparison")

    assert not (tmp_path / "comparison").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", ""),
        ("research_date", "invalid"),
        ("research_tools", [""]),
        ("specialist_plugins_exposed", ["vera"]),
    ],
)
def test_unusable_or_contaminated_baseline_configuration_is_rejected(
    tmp_path, evaluation, field, value
):
    spec = _spec(tmp_path)
    path = tmp_path / "host.json"
    config = json.loads(path.read_text())
    config[field] = value
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        evaluation.record_evaluation(tmp_path, spec)
    assert not (tmp_path / "evaluation_runs").exists()


def test_missing_inventoried_capture_is_rejected_before_copying(tmp_path, evaluation):
    spec = _spec(tmp_path, "vera")
    (tmp_path / "capture.txt").write_text("Actual extracted evidence.")
    (tmp_path / "source_inventory.json").write_text(
        json.dumps(
            {
                "sources": [
                    {"source_id": "source-001", "captured_text_path": "capture.txt"}
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="every inventoried"):
        evaluation.record_evaluation(tmp_path, spec)
    assert not (tmp_path / "evaluation_runs").exists()


def test_retained_capture_keeps_original_locator_and_is_checked_on_reopen(
    tmp_path, evaluation
):
    spec = _spec(tmp_path, "vera")
    (tmp_path / "capture.txt").write_text("Actual extracted evidence.")
    (tmp_path / "source_inventory.json").write_text(
        json.dumps(
            {
                "sources": [
                    {"source_id": "source-001", "captured_text_path": "capture.txt"}
                ]
            }
        )
    )
    spec["artifacts"].append({"role": "source_capture", "path": "capture.txt"})
    run = evaluation.record_evaluation(tmp_path, spec)
    record = evaluation.verify_evaluation(run)
    item = next(
        item for item in record["artifacts"] if item["role"] == "source_capture"
    )
    assert item["original_path"] == "capture.txt"
    (run / item["path"]).write_text("Changed evidence.")
    with pytest.raises(ValueError, match="artifact changed"):
        evaluation.verify_evaluation(run)


def test_duplicate_run_cannot_be_exported_as_a_comparison(tmp_path, evaluation):
    run = evaluation.record_evaluation(tmp_path, _spec(tmp_path))
    with pytest.raises(ValueError, match="distinct"):
        evaluation.export_blinded_comparison([run, run], tmp_path / "comparison")


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "different-model"),
        ("research_tools", ["other-tool"]),
        ("research_date", "2026-10-14"),
    ],
)
def test_unequal_model_tools_or_date_prevent_blind_comparison(
    tmp_path, evaluation, field, value
):
    first = tmp_path / "first"
    second = tmp_path / "second"
    a = _spec(first, identifier="a")
    b = _spec(second, identifier="b")
    config = json.loads((second / "host.json").read_text())
    config[field] = value
    (second / "host.json").write_text(json.dumps(config))
    runs = [
        evaluation.record_evaluation(first, a),
        evaluation.record_evaluation(second, b),
    ]
    with pytest.raises(ValueError, match="same assignment"):
        evaluation.export_blinded_comparison(runs, tmp_path / "comparison")


def test_cli_retains_and_verifies_an_actual_run(
    tmp_path, evaluation, monkeypatch, capsys
):
    import sys

    spec = _spec(tmp_path)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "research_evaluation.py",
            "record",
            "--root",
            str(tmp_path),
            "--specification",
            str(path),
        ],
    )
    assert evaluation.main() == 0
    run = Path(json.loads(capsys.readouterr().out))
    monkeypatch.setattr(
        sys, "argv", ["research_evaluation.py", "verify", "--run", str(run)]
    )
    assert evaluation.main() == 0
    assert json.loads(capsys.readouterr().out)["quality"] == "not_assessed_by_helper"


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize(
    ("host", "skill"),
    [("plugin", "deep-research"), ("claude-plugin", "mparanza-deep-research")],
)
def test_packaged_evaluation_preserves_the_requested_codex_comparator(
    product, host, skill
):
    root = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(
        root / f"plugin_packages/{product}/{product}-{host}.zip"
    ) as package:
        suffix = (
            f"modules/deep-research-validator/skills/{skill}/references/evaluation.md"
        )
        path = next(name for name in package.namelist() if name.endswith(suffix))
        guidance = package.read(path).decode("utf-8")
    assert "the `standard_codex` baseline's output" in guidance
    assert "standard Claude" not in guidance
