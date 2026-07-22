from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
VALIDATOR = (
    VERA_ROOT
    / "skills"
    / "privacy-surface-review"
    / "scripts"
    / "validate_privacy_surfaces.py"
)
CONTEXT_POLICY = "real_case_data_may_enter_codex_context"


def _validator_module():
    spec = importlib.util.spec_from_file_location("vera_privacy_validator", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VERA_ROOT / "privacy" / "workstreams").glob("*.json"))
    ]


def test_vera_privacy_register_covers_current_workstreams_and_is_fresh() -> None:
    validator = _validator_module()

    errors = validator.validate_privacy_surfaces(VERA_ROOT)

    assert errors == []


def test_vera_privacy_manifests_match_the_published_schema() -> None:
    schema = json.loads(
        (VERA_ROOT / "privacy" / "privacy-surface.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    errors = {
        str(manifest["workstream"]): [
            error.message for error in validator.iter_errors(manifest)
        ]
        for manifest in _manifests()
    }

    assert errors
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_vera_privacy_contract_allows_real_case_data_without_minimum_classifier() -> (
    None
):
    forbidden_fields = {
        "commercialista_notice",
        "data_flow",
        "full_source_expected",
        "minimum_necessary",
        "residual_risks",
        "semantic_reasoning_required",
    }

    for manifest in _manifests():
        assert manifest["schema_version"] == 2
        codex_context = manifest["codex_context"]
        assert codex_context["policy"] == CONTEXT_POLICY
        assert codex_context["classes"]
        assert forbidden_fields.isdisjoint(manifest)
        for context_class in codex_context["classes"]:
            assert forbidden_fields.isdisjoint(context_class)


def test_vera_account_boundary_is_explicit_and_not_a_per_case_form() -> None:
    expected_items = [
        "account_or_workspace_plan",
        "model_training_data_controls",
        "retention_and_deletion_controls",
    ]

    for manifest in _manifests():
        boundary = manifest["codex_account_boundary"]
        assert boundary == {
            "selected_by": "firm_or_user",
            "vera_runtime_enforcement": "none",
            "review_timing": "before_professional_use_and_when_account_or_terms_change",
            "review_items": expected_items,
            "per_case_record_required": False,
        }


def test_vera_external_confirmations_are_limited_to_optional_boundaries() -> None:
    for manifest in _manifests():
        assert isinstance(manifest["boundaries_beyond_codex"], list)
        for boundary in manifest["boundaries_beyond_codex"]:
            if boundary["requires_confirmation"]:
                assert boundary["optional"] is True


def test_vera_workflow_wrappers_do_not_show_routine_privacy_notices() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    roles = components.get("workflow_roles", {})

    for workstream in components["plugins"]:
        if roles.get(workstream, {}).get("kind") == "internal_engine":
            continue
        wrapper = VERA_ROOT / "skills" / workstream / "SKILL.md"
        text = wrapper.read_text(encoding="utf-8")
        assert "## Privacy Boundary" not in text
        assert "commercialista_notice" not in text


def test_vera_governance_uses_the_selected_account_boundary_without_double_confirmation() -> (
    None
):
    readme = (VERA_ROOT / "README.md").read_text(encoding="utf-8")
    umbrella = (VERA_ROOT / "skills" / "vera" / "SKILL.md").read_text(encoding="utf-8")
    review = (VERA_ROOT / "skills" / "privacy-surface-review" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "account boundary selected by the firm or user" in readme
    assert "account boundary selected by the firm or user" in umbrella
    assert "approved Codex" not in readme
    assert "approved Codex" not in umbrella
    assert "do not ask again" in umbrella
    assert "do not ask again" in review


def test_vera_component_guidance_avoids_fake_minimums_and_ambiguous_authority() -> None:
    new_client = (
        ROOT / "plugins" / "new-client" / "skills" / "new-client" / "SKILL.md"
    ).read_text(encoding="utf-8")
    registro_skill = (
        ROOT
        / "plugins"
        / "registro-imprese-sari"
        / "skills"
        / "registro-imprese-sari"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    registro_sources = (
        ROOT
        / "plugins"
        / "registro-imprese-sari"
        / "references"
        / "official-sources.md"
    ).read_text(encoding="utf-8")

    assert "client-relationship privacy role or processing basis" in new_client
    assert "processing authority" not in new_client
    assert "minimum metadata needed for provenance" not in registro_skill
    assert "register minimal metadata" not in registro_sources


def test_vera_privacy_validator_reports_unregistered_manifest_gap(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    missing = vera_root / "privacy" / "workstreams" / "check-entries.json"
    missing.unlink()

    errors = validator.validate_privacy_surfaces(vera_root)

    assert "check-entries: registered workstream has no privacy manifest" in errors


def test_vera_privacy_validator_detects_changed_governed_source(
    tmp_path: Path,
) -> None:
    plugins_root = tmp_path / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "prompt-optimizer"
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "prompt-optimizer", component_root)
    shared_server = tmp_path / "scripts" / "serve_review_workbench.py"
    shared_server.parent.mkdir()
    shutil.copy2(ROOT / "scripts" / "serve_review_workbench.py", shared_server)
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["prompt-optimizer"]
    components["workflow_roles"] = {}
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n", encoding="utf-8"
    )
    manifest_dir = vera_root / "privacy" / "workstreams"
    for manifest in manifest_dir.glob("*.json"):
        if manifest.stem != "prompt-optimizer":
            manifest.unlink()
    validator_path = (
        vera_root
        / "skills"
        / "privacy-surface-review"
        / "scripts"
        / "validate_privacy_surfaces.py"
    )
    refreshed = subprocess.run(
        [sys.executable, str(validator_path), "--refresh", "prompt-optimizer"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    governed_adapter = component_root / "assets" / "review-workbench-adapter.json"
    governed_adapter.write_text(
        governed_adapter.read_text(encoding="utf-8")
        + "\nMaterial browser-boundary change.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(validator_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "prompt-optimizer: privacy review is stale" in result.stdout


def test_privacy_fingerprint_governs_projected_local_review_server(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    repository_root = tmp_path / "repository"
    plugins_root = repository_root / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "client-file-preparation"
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "client-file-preparation", component_root)
    shared_server = repository_root / "scripts" / "serve_review_workbench.py"
    shared_server.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "serve_review_workbench.py", shared_server)

    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["client-file-preparation"]
    components["workflow_roles"] = {
        "client-file-preparation": {"kind": "internal_engine"}
    }
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_dir = vera_root / "privacy" / "workstreams"
    for manifest in manifest_dir.glob("*.json"):
        if manifest.stem != "client-file-preparation":
            manifest.unlink()
    validator._refresh("client-file-preparation", vera_root)

    assert validator.validate_privacy_surfaces(vera_root) == []

    packaged_component = vera_root / "modules" / "client-file-preparation"
    shutil.copytree(component_root, packaged_component)
    shutil.copy2(shared_server, packaged_component / "scripts" / "review_server.py")
    assert validator.validate_privacy_surfaces(vera_root) == []

    shared_server.write_text(
        shared_server.read_text(encoding="utf-8") + "\n# privacy material change\n",
        encoding="utf-8",
    )
    shutil.rmtree(packaged_component)
    assert (
        "client-file-preparation: privacy review is stale; run the review skill, then --refresh"
        in validator.validate_privacy_surfaces(vera_root)
    )


def test_vera_privacy_validator_rejects_confirmation_on_required_boundary(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    manifest_path = (
        vera_root / "privacy" / "workstreams" / "deep-research-validator.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["boundaries_beyond_codex"][0]["requires_confirmation"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    errors = validator.validate_privacy_surfaces(vera_root)

    assert (
        "deep-research-validator: confirmation is allowed only for an optional boundary"
        in errors
    )
