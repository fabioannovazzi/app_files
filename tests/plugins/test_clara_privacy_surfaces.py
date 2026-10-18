from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
VALIDATOR = (
    CLARA_ROOT
    / "skills"
    / "privacy-surface-review"
    / "scripts"
    / "validate_privacy_surfaces.py"
)
CONTEXT_POLICY = "real_case_data_may_enter_selected_runtime_model_context"
EXPECTED_HOSTED_SERVICES = {
    "operational-incidents",
    "workflow-usage",
    "run-receipt-stamping",
    "hosted-interviews",
    "hosted-voice",
    "plugin-feedback",
    "plugin-update-check",
    "research-video-voice",
    "retail-data",
    "prepared-course-files",
    "managed-python-runtime",
}


def _validator_module():
    spec = importlib.util.spec_from_file_location("clara_privacy_validator", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifests(directory: str) -> list[dict[str, Any]]:
    return _load_json_manifests(CLARA_ROOT / "privacy" / directory)


def _load_json_manifests(directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def test_clara_privacy_register_covers_every_user_facing_skill_and_is_fresh() -> None:
    validator = _validator_module()

    errors = validator.validate_privacy_surfaces(CLARA_ROOT)

    assert errors == []


def test_clara_workflow_manifests_match_published_schema() -> None:
    schema = json.loads(
        (CLARA_ROOT / "privacy" / "privacy-surface.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    errors = {
        manifest["workstream"]: [
            error.message for error in validator.iter_errors(manifest)
        ]
        for manifest in _manifests("workstreams")
    }

    assert errors
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_clara_hosted_service_manifests_match_published_schema() -> None:
    schema = json.loads(
        (CLARA_ROOT / "privacy" / "service-boundary.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    manifests = _manifests("services")
    errors = {
        manifest["service_id"]: [
            error.message for error in validator.iter_errors(manifest)
        ]
        for manifest in manifests
    }

    assert {
        manifest["service_id"] for manifest in manifests
    } == EXPECTED_HOSTED_SERVICES
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_clara_codex_boundary_allows_real_professional_data_without_case_forms() -> (
    None
):
    profiles = json.loads((CLARA_ROOT / "privacy/runtime-profiles.json").read_text())[
        "profiles"
    ]
    assert len(profiles) == 4
    assert all(
        profile["account_boundary"]["product_runtime_enforcement"] == "none"
        for profile in profiles
    )
    assert all(
        profile["account_boundary"]["per_case_record_required"] is False
        for profile in profiles
    )
    assert all(
        profile["model_processing"]["automatic_anonymization"] is False
        for profile in profiles
    )
    forbidden_fields = {
        "commercialista_notice",
        "minimum_necessary",
        "minimum_useful_context",
        "personal_data_detected",
        "per_prompt_record",
        "runtime_consent",
    }

    for manifest in _manifests("workstreams"):
        assert manifest["model_context"]["policy"] == CONTEXT_POLICY
        assert manifest["model_context"]["classes"]
        assert forbidden_fields.isdisjoint(manifest)


def test_clara_privacy_validator_allows_an_honest_empty_security_control_list() -> None:
    validator = _validator_module()

    assert (
        validator._security_control_errors([], scope="workflow without controls") == []
    )


def test_clara_register_does_not_relabel_workflow_hygiene_as_security() -> None:
    manifests = {
        manifest["workstream"]: manifest for manifest in _manifests("workstreams")
    }
    ceremonial_ids = {
        "local-artifacts",
        "local-case-workspace",
        "local-durable-copy",
        "local-output-review",
        "no-automatic-anonymisation",
        "no-certification-claim",
        "pending-judgement-gate",
        "preserve-raw-source",
        "procedural-preview-and-consent",
        "procedural-sanitization-instruction",
        "semantic-boundary",
    }

    assert manifests["claim-basis-map"]["security_controls"] == []
    # The native budget preview now enforces receipt/script identity and an
    # opaque-origin loopback sandbox; these are executable controls, not
    # workflow hygiene. Their behavior is exercised in test_clara_budget_preview.
    assert [
        control["id"] for control in manifests["reporting-engine"]["security_controls"]
    ] == ["local-budget-preview"]
    assert manifests["transcribe"]["security_controls"] == []
    assert all(
        control["id"] not in ceremonial_ids
        for manifest in [
            *_manifests("workstreams"),
            *_manifests("services"),
        ]
        for control in manifest["security_controls"]
    )


def test_hosted_voice_launch_token_is_not_documented_as_authentication() -> None:
    services = {manifest["service_id"]: manifest for manifest in _manifests("services")}
    voice = services["hosted-voice"]

    assert (
        "not standalone authentication"
        in voice["service_details"]["access"]["arrangement"]
    )
    assert "launch-token-only" in " ".join(
        voice["service_details"]["access"]["controls"]
    )


def test_clara_hosted_records_use_source_backed_retention_and_cleanup() -> None:
    manifests = {
        manifest["service_id"]: manifest for manifest in _manifests("services")
    }

    interview_retention = manifests["hosted-interviews"]["service_details"]["retention"]
    assert interview_retention["status"] == "documented"
    assert "manual or administrative deletion" in interview_retention["statement"]
    assert "link expiry" in interview_retention["statement"]

    voice = manifests["hosted-voice"]
    assert voice["service_details"]["retention"]["status"] == "documented"
    assert (
        "transcript and job state are scrubbed"
        in voice["service_details"]["retention"]["statement"]
    )
    assert any(
        item["id"] == "live-capture"
        and "screen video" in item["content"].lower()
        and "not uploaded" in item["content"].lower()
        for item in voice["service_details"]["data_sent"]
    )

    assert (
        manifests["retail-data"]["service_details"]["retention"]["status"]
        == "documented"
    )
    retail_retention = manifests["retail-data"]["service_details"]["retention"][
        "statement"
    ]
    assert "durable service data" in retail_retention
    assert "no age-based or event-triggered automatic deletion" in retail_retention
    assert "reject new work without deleting retained artifacts" in retail_retention

    research_video_voice = manifests["research-video-voice"]
    assert (
        research_video_voice["service_details"]["retention"]["status"]
        == "partially_documented"
    )
    assert (
        "without writing narration requests or audio"
        in research_video_voice["service_details"]["retention"]["statement"]
    )
    assert (
        "not established by the inspected application source"
        in research_video_voice["service_details"]["retention"]["statement"]
    )


def test_clara_register_includes_non_case_automatic_network_boundaries() -> None:
    services = {manifest["service_id"]: manifest for manifest in _manifests("services")}
    update = services["plugin-update-check"]
    feedback = services["plugin-feedback"]

    assert update["external_boundaries"][0]["activation"] == "automatic_session_start"
    assert (
        "no client files, prompts, transcripts, or case content"
        in update["service_details"]["data_sent"][0]["content"]
    )
    assert any(
        item["activation"] == "automatic_after_prior_submission"
        for item in feedback["external_boundaries"]
    )
    assert any(
        item["id"] == "automatic-status-poll"
        for item in feedback["service_details"]["data_sent"]
    )
    approved_text = next(
        item
        for item in feedback["service_details"]["data_sent"]
        if item["id"] == "approved-text-request"
    )
    assert "helper enforces that mechanical shape" in approved_text["content"]
    assert "does not detect personal data" in approved_text["content"]
    assert any(
        item["id"] == "approved-follow-up-evidence"
        for item in feedback["service_details"]["data_sent"]
    )


def test_vera_and_clara_share_maintenance_boundary_semantics() -> None:
    vera_services = {
        manifest["service_id"]: manifest
        for manifest in _load_json_manifests(
            ROOT / "plugins" / "vera" / "privacy" / "services"
        )
    }
    clara_services = {
        manifest["service_id"]: manifest for manifest in _manifests("services")
    }
    common_ids = {"plugin-update-check", "plugin-feedback"}

    assert common_ids <= vera_services.keys()
    assert common_ids <= clara_services.keys()

    vera_update_boundaries = vera_services["plugin-update-check"]["external_boundaries"]
    clara_update_payloads = clara_services["plugin-update-check"]["service_details"][
        "data_sent"
    ]
    assert [boundary["id"] for boundary in vera_update_boundaries] == [
        "automatic-version-check"
    ]
    assert [payload["id"] for payload in clara_update_payloads] == [
        "version-manifest-request"
    ]
    assert "HTTP GET" in vera_update_boundaries[0]["content"]
    assert "HTTPS GET" in clara_update_payloads[0]["content"]

    vera_feedback_boundaries = vera_services["plugin-feedback"]["external_boundaries"]
    clara_feedback_payloads = clara_services["plugin-feedback"]["service_details"][
        "data_sent"
    ]
    assert any(
        boundary["activation"] == "explicit_user_choice"
        for boundary in vera_feedback_boundaries
    )
    assert any(
        boundary["activation"] == "automatic_after_prior_submission"
        for boundary in vera_feedback_boundaries
    )
    assert any(
        payload["id"] == "approved-text-request" for payload in clara_feedback_payloads
    )
    assert any(
        payload["id"] == "automatic-status-poll" for payload in clara_feedback_payloads
    )


def test_clara_external_confirmations_are_only_for_unselected_optional_actions() -> (
    None
):
    manifests = _manifests("workstreams")

    for manifest in manifests:
        for boundary in manifest["external_boundaries"]:
            if boundary["requires_confirmation"]:
                assert boundary["optional"] is True
                assert boundary["id"] in {
                    "approved-managed-ocr-runtime",
                    "approved-research-video-voice",
                    "bounded-authorized-public-research",
                    "consented-plugin-feedback",
                    "openai-speech-generation",
                    "planning-public-research",
                    "planning-sites-report",
                    "budget-sites-report",
                    "send-participant-link",
                }


def _minimal_clara(tmp_path: Path) -> Path:
    """Keep one real reviewed workflow and its local dependencies."""
    root = tmp_path / "plugins/clara"
    shutil.copytree(CLARA_ROOT, root)
    registry = json.loads((root / "privacy/registry.json").read_text())
    entry = registry["workstreams"]["claim-basis-map"]
    entry["components"] = []
    entry["public_pages"] = []
    registry["workstreams"] = {"claim-basis-map": entry}
    registry["services"] = []
    registry.pop("host_omissions", None)
    (root / "privacy/registry.json").write_text(json.dumps(registry))
    (root / "components.json").write_text(json.dumps({"plugins": []}))
    (root / "usage/pipelines.json").unlink()
    for folder in (root / "skills").iterdir():
        if folder.name not in {"claim-basis-map", "privacy-surface-review"}:
            shutil.rmtree(folder)
    for file in (root / "privacy/workstreams").glob("*.json"):
        if file.stem != "claim-basis-map":
            file.unlink()
    for file in (root / "privacy/services").glob("*.json"):
        file.unlink()
    path = root / "privacy/workstreams/claim-basis-map.json"
    manifest = json.loads(path.read_text())
    manifest["public_explanations"] = {}
    manifest["service_ids"] = []
    path.write_text(json.dumps(manifest))
    return root


def test_clara_privacy_validator_detects_changed_governed_source(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    root = _minimal_clara(tmp_path)
    validator._refresh("claim-basis-map", root)
    assert validator.validate_privacy_surfaces(root) == []
    script = root / "skills/claim-basis-map/scripts/render_claim_basis_map.py"
    script.write_text(script.read_text() + "\n# reviewed boundary changed\n")

    errors = validator.validate_privacy_surfaces(root)

    assert (
        "claim-basis-map: privacy review is stale; run the review skill, then --refresh"
        in errors
    )


def test_clara_privacy_validator_reports_new_skill_without_manifest(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    root = _minimal_clara(tmp_path)
    skill = root / "skills/future-workflow/SKILL.md"
    skill.parent.mkdir()
    skill.write_text("---\nname: future-workflow\n---\n")

    errors = validator.validate_privacy_surfaces(root)

    assert "future-workflow: skill has no privacy registration" in errors
