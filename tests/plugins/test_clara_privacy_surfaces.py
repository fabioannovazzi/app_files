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
CONTEXT_POLICY = "real_professional_data_may_enter_codex_context"
EXPECTED_HOSTED_SERVICES = {
    "hosted-interviews",
    "hosted-voice",
    "plugin-feedback",
    "plugin-update-check",
    "retail-data",
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
        (CLARA_ROOT / "privacy" / "workflow-privacy-surface.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    errors = {
        manifest["workflow"]: [
            error.message for error in validator.iter_errors(manifest)
        ]
        for manifest in _manifests("workflows")
    }

    assert errors
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_clara_hosted_service_manifests_match_published_schema() -> None:
    schema = json.loads(
        (CLARA_ROOT / "privacy" / "hosted-service.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    manifests = _manifests("hosted-services")
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
    expected_ordinary_processing = {
        "scope": "content_supplied_to_the_codex_model",
        "account_arrangement": "user_selected_chatgpt_or_codex_account",
        "separate_clara_recipient_or_arrangement": False,
        "automatic_anonymisation": False,
        "local_filter_or_aggregate": "only_when_useful_for_professional_work",
        "plan_visibility": "not_inspected_or_enforced_by_clara",
    }
    expected_account_boundary = {
        "selected_by": "firm_or_user",
        "clara_runtime_enforcement": "none",
        "review_timing": "before_professional_use_and_when_account_or_terms_change",
        "review_items": [
            "account_or_workspace_plan",
            "model_training_data_controls",
            "retention_and_deletion_controls",
        ],
        "per_case_record_required": False,
    }
    forbidden_fields = {
        "commercialista_notice",
        "minimum_necessary",
        "minimum_useful_context",
        "personal_data_detected",
        "per_prompt_record",
        "runtime_consent",
    }

    for manifest in _manifests("workflows"):
        assert manifest["codex_context"]["policy"] == CONTEXT_POLICY
        assert manifest["codex_context"]["classes"]
        assert (
            manifest["ordinary_codex_model_processing"] == expected_ordinary_processing
        )
        assert manifest["codex_account_boundary"] == expected_account_boundary
        assert forbidden_fields.isdisjoint(manifest)


def test_clara_privacy_validator_allows_an_honest_empty_security_control_list() -> None:
    validator = _validator_module()

    assert validator._control_errors([], subject="workflow without controls") == []


def test_clara_register_does_not_relabel_workflow_hygiene_as_security() -> None:
    manifests = {manifest["workflow"]: manifest for manifest in _manifests("workflows")}
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

    assert manifests["beautify-deck"]["security_controls"] == []
    assert manifests["claim-basis-map"]["security_controls"] == []
    assert manifests["reporting-engine"]["security_controls"] == []
    assert manifests["transcribe"]["security_controls"] == []
    assert all(
        control["id"] not in ceremonial_ids
        for manifest in [
            *_manifests("workflows"),
            *_manifests("hosted-services"),
        ]
        for control in manifest["security_controls"]
    )


def test_hosted_voice_launch_token_is_not_documented_as_authentication() -> None:
    services = {
        manifest["service_id"]: manifest for manifest in _manifests("hosted-services")
    }
    voice = services["hosted-voice"]

    assert "not standalone authentication" in voice["access"]["arrangement"]
    assert "launch-token-only" in " ".join(voice["access"]["controls"])


def test_clara_hosted_records_use_source_backed_retention_and_cleanup() -> None:
    manifests = {
        manifest["service_id"]: manifest for manifest in _manifests("hosted-services")
    }

    interview_retention = manifests["hosted-interviews"]["retention"]
    assert interview_retention["status"] == "documented"
    assert "manual or administrative deletion" in interview_retention["statement"]
    assert "link expiry" in interview_retention["statement"]

    voice = manifests["hosted-voice"]
    assert voice["retention"]["status"] == "documented"
    assert "transcript and job state are scrubbed" in voice["retention"]["statement"]
    assert any(
        item["id"] == "live-capture"
        and "screen video" in item["content"].lower()
        and "not uploaded" in item["content"].lower()
        for item in voice["data_sent"]
    )

    assert manifests["retail-data"]["retention"]["status"] == ("partially_documented")
    retail_retention = manifests["retail-data"]["retention"]["statement"]
    assert all(
        period in retail_retention for period in ("30 days", "7 days", "180 days")
    )


def test_clara_register_includes_non_case_automatic_network_boundaries() -> None:
    services = {
        manifest["service_id"]: manifest for manifest in _manifests("hosted-services")
    }
    update = services["plugin-update-check"]
    feedback = services["plugin-feedback"]

    assert update["automatic"] is True
    assert (
        "no client files, prompts, transcripts, or case content"
        in update["data_sent"][0]["content"]
    )
    assert feedback["automatic"] is True
    assert any(item["id"] == "automatic-status-poll" for item in feedback["data_sent"])
    approved_text = next(
        item for item in feedback["data_sent"] if item["id"] == "approved-text-request"
    )
    assert "helper accepts arbitrary JSON" in approved_text["content"]
    assert "does not detect personal data" in approved_text["content"]


def test_vera_and_clara_share_maintenance_boundary_semantics() -> None:
    vera_services = {
        manifest["service_id"]: manifest
        for manifest in _load_json_manifests(
            ROOT / "plugins" / "vera" / "privacy" / "services"
        )
    }
    clara_services = {
        manifest["service_id"]: manifest for manifest in _manifests("hosted-services")
    }
    common_ids = {"plugin-update-check", "plugin-feedback"}

    assert common_ids <= vera_services.keys()
    assert common_ids <= clara_services.keys()

    vera_update_boundaries = vera_services["plugin-update-check"][
        "boundaries_beyond_codex"
    ]
    clara_update_payloads = clara_services["plugin-update-check"]["data_sent"]
    assert [boundary["id"] for boundary in vera_update_boundaries] == [
        "automatic-version-check"
    ]
    assert [payload["id"] for payload in clara_update_payloads] == [
        "version-manifest-request"
    ]
    assert "HTTP GET" in vera_update_boundaries[0]["content"]
    assert "HTTPS GET" in clara_update_payloads[0]["content"]

    vera_feedback_boundaries = vera_services["plugin-feedback"][
        "boundaries_beyond_codex"
    ]
    clara_feedback_payloads = clara_services["plugin-feedback"]["data_sent"]
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
    manifests = _manifests("workflows")

    for manifest in manifests:
        for boundary in manifest["boundaries_beyond_codex"]:
            if boundary["requires_confirmation"]:
                assert boundary["optional"] is True
                assert boundary["id"] in {
                    "consented-plugin-feedback",
                    "send-participant-link",
                }


def test_clara_privacy_validator_detects_changed_governed_source(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    clara_root = tmp_path / "plugins" / "clara"
    skill_source = CLARA_ROOT / "skills" / "claim-basis-map"
    skill_target = clara_root / "skills" / "claim-basis-map"
    shutil.copytree(skill_source, skill_target)
    manifest_dir = clara_root / "privacy" / "workflows"
    manifest_dir.mkdir(parents=True)
    shutil.copy2(
        CLARA_ROOT / "privacy" / "workflows" / "claim-basis-map.json",
        manifest_dir / "claim-basis-map.json",
    )
    (clara_root / "privacy" / "hosted-services").mkdir(parents=True)
    governed_script = skill_target / "scripts" / "render_claim_basis_map.py"
    governed_script.write_text(
        governed_script.read_text(encoding="utf-8") + "\n# reviewed boundary changed\n",
        encoding="utf-8",
    )

    errors = validator.validate_privacy_surfaces(clara_root)

    assert (
        "workflow claim-basis-map: privacy review is stale; review source, then --refresh"
        in errors
    )


def test_clara_privacy_validator_reports_new_skill_without_manifest(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    clara_root = tmp_path / "plugins" / "clara"
    (clara_root / "skills" / "future-workflow").mkdir(parents=True)
    (clara_root / "skills" / "future-workflow" / "SKILL.md").write_text(
        "---\nname: future-workflow\n---\n",
        encoding="utf-8",
    )
    (clara_root / "privacy" / "workflows").mkdir(parents=True)
    (clara_root / "privacy" / "hosted-services").mkdir(parents=True)

    errors = validator.validate_privacy_surfaces(clara_root)

    assert (
        "workflow future-workflow: registered skill has no privacy manifest" in errors
    )
