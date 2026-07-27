from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
VALIDATOR = (
    VERA_ROOT
    / "skills"
    / "privacy-surface-review"
    / "scripts"
    / "validate_privacy_surfaces.py"
)
RUNTIME_PROFILE_IDS = ["openai-codex", "anthropic-cowork"]


def _validator_module():
    spec = importlib.util.spec_from_file_location("vera_cowork_privacy", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_profiles() -> dict[str, dict[str, Any]]:
    payload = json.loads(
        (VERA_ROOT / "privacy" / "runtime-profiles.json").read_text(encoding="utf-8")
    )
    return {profile["id"]: profile for profile in payload["profiles"]}


def _workstream_manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VERA_ROOT / "privacy" / "workstreams").glob("*.json"))
    ]


def _service_manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VERA_ROOT / "privacy" / "services").glob("*.json"))
    ]


def test_vera_runtime_catalog_has_codex_and_cowork_without_chat_surface() -> None:
    profiles = _runtime_profiles()

    assert list(profiles) == RUNTIME_PROFILE_IDS
    assert profiles["openai-codex"]["surfaces"] == ["codex"]
    assert profiles["anthropic-cowork"]["surfaces"] == ["cowork"]
    assert all(
        "chat" not in surface
        for profile in profiles.values()
        for surface in profile["surfaces"]
    )


def test_vera_cowork_profile_declares_anthropic_model_and_account_boundary() -> None:
    cowork = _runtime_profiles()["anthropic-cowork"]

    assert cowork["provider"] == "Anthropic"
    assert cowork["runtime"] == "Cowork"
    assert cowork["account_boundary"]["selected_by"] == "firm_or_user"
    assert cowork["account_boundary"]["vera_runtime_enforcement"] == "none"
    assert cowork["account_boundary"]["per_case_record_required"] is False
    assert (
        cowork["model_processing"]["scope"]
        == "ordinary_anthropic_cowork_model_processing"
    )
    assert "Anthropic" in cowork["model_processing"]["destination"]
    assert cowork["model_processing"]["local_only"] is False
    assert cowork["model_processing"]["automatic_anonymization"] is False


def test_vera_workstreams_share_one_manifest_across_both_runtimes() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    manifests = _workstream_manifests()

    assert {manifest["workstream"] for manifest in manifests} == set(
        components["plugins"]
    )
    assert all(manifest["schema_version"] == 3 for manifest in manifests)
    assert all(
        manifest["runtime_profiles"] == RUNTIME_PROFILE_IDS for manifest in manifests
    )
    assert all(
        model_class["runtime_profiles"]
        for manifest in manifests
        for model_class in manifest["model_context"]["classes"]
    )


def test_vera_external_routes_name_their_applicable_runtime_profiles() -> None:
    manifests = {
        manifest["workstream"]: manifest for manifest in _workstream_manifests()
    }
    studio = manifests["studio-archive"]
    studio_boundaries = {
        boundary["id"]: boundary for boundary in studio["external_boundaries"]
    }
    studio_context = {
        model_class["id"]: model_class
        for model_class in studio["model_context"]["classes"]
    }
    research_boundaries = manifests["deep-research-validator"]["external_boundaries"]
    inps_boundaries = {
        boundary["id"]: boundary
        for boundary in manifests["previdenza-inps"]["external_boundaries"]
    }

    assert studio_boundaries
    assert studio_context["gmail-client-evidence"]["runtime_profiles"] == (
        RUNTIME_PROFILE_IDS
    )
    assert studio_boundaries["codex-gmail-client-search"]["runtime_profiles"] == [
        "openai-codex"
    ]
    assert studio_boundaries["anthropic-cowork-gmail-client-search"][
        "runtime_profiles"
    ] == ["anthropic-cowork"]
    assert studio_boundaries["codex-whatsapp-desktop-client-review"][
        "runtime_profiles"
    ] == ["openai-codex"]
    assert inps_boundaries["inps-browser-capture"]["runtime_profiles"] == [
        "openai-codex"
    ]
    assert research_boundaries[0]["runtime_profiles"] == RUNTIME_PROFILE_IDS


def test_vera_current_shared_services_are_not_claimed_as_cowork_routes() -> None:
    manifests = _service_manifests()

    assert all(
        manifest["runtime_profiles"] == ["openai-codex"] for manifest in manifests
    )
    assert all(
        boundary["runtime_profiles"] == ["openai-codex"]
        for manifest in manifests
        for boundary in manifest["external_boundaries"]
    )


def test_vera_validator_rejects_a_false_cowork_local_only_claim(
    tmp_path: Path,
) -> None:
    vera_root = tmp_path / "plugins" / "vera"
    privacy_root = vera_root / "privacy"
    (privacy_root / "workstreams").mkdir(parents=True)
    (privacy_root / "services").mkdir()
    (vera_root / "components.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plugins": [],
                "shared_services": [],
                "workflow_roles": {},
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(
        (VERA_ROOT / "privacy" / "runtime-profiles.json").read_text(encoding="utf-8")
    )
    payload["profiles"][1]["model_processing"]["local_only"] = True
    (privacy_root / "runtime-profiles.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    validator = _validator_module()

    errors = validator.validate_privacy_surfaces(vera_root)

    assert (
        "runtime-profiles: anthropic-cowork account or model-processing "
        "boundary is inaccurate" in errors
    )
