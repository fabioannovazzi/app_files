from __future__ import annotations

import copy
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins" / "browser-automation"
VERA = ROOT / "plugins" / "vera"
CONTRACT_PATH = COMPONENT / "scripts" / "capability_pipeline.py"
DEPENDENCY_CHECK_PATH = COMPONENT / "scripts" / "check_dependencies.py"
CAPABILITIES = COMPONENT / "capabilities"


def _load_pipeline_test_helpers() -> ModuleType:
    """Load shared v2 test builders without changing Python import paths."""

    spec = importlib.util.spec_from_file_location(
        "test_browser_pipeline_shared_helpers",
        ROOT / "tests" / "test_browser_automation_pipeline.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_contract() -> ModuleType:
    """Load the browser capability contract from canonical source."""

    spec = importlib.util.spec_from_file_location(
        "test_browser_capability_pipeline_legacy_migration", CONTRACT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_dependency_check() -> ModuleType:
    """Load the public dependency-check command from canonical source."""

    spec = importlib.util.spec_from_file_location(
        "test_browser_dependency_check", DEPENDENCY_CHECK_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checked_in_capability(capability_id: str) -> dict[str, object]:
    """Return one checked-in capability payload without fixture normalization."""

    path = CAPABILITIES / capability_id / "capability.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _capability(capability_id: str) -> dict[str, object]:
    """Return a draft Gmail fixture for contract mutation tests."""

    payload = _checked_in_capability(capability_id)
    if capability_id != "gmail-search-export":
        return payload
    payload["status"] = "draft"
    payload["validation"] = {
        "environment_scope": "not_validated",
        "execution_contract_sha256": None,
        "receipts": [],
        "known_limits": copy.deepcopy(payload["validation"]["known_limits"]),
    }
    payload["provenance"]["source"] = "live_discovery_unreviewed"
    payload["provenance"]["discovery_approval_id"] = None
    payload["provenance"]["discovery_approved_at"] = None
    return payload


def _set_nested(
    payload: dict[str, object], path: tuple[object, ...], value: object
) -> None:
    """Set one nested JSON-like value for a parametrized invalid case."""

    target: object = payload
    for part in path[:-1]:
        if isinstance(part, int):
            assert isinstance(target, list)
            target = target[part]
        else:
            assert isinstance(target, dict)
            target = target[part]
    final = path[-1]
    if isinstance(final, int):
        assert isinstance(target, list)
        target[final] = value
    else:
        assert isinstance(target, dict)
        target[final] = value


def test_three_process_capabilities_have_honest_contract_states() -> None:
    contract = _load_contract()
    expected_status = {
        "gmail-search-export": "draft",
        "agenzia-invoice-zip": "scaffold",
        "teamsystem-process": "scaffold",
    }

    actual_status = {}
    for capability_id, status in expected_status.items():
        payload = _checked_in_capability(capability_id)
        actual_status[capability_id] = payload["status"]
        assert contract.validate_capability(payload) == []

    assert actual_status == expected_status


def test_gmail_export_draft_retains_process_but_requires_new_replays() -> None:
    payload = _checked_in_capability("gmail-search-export")

    assert payload["status"] == "draft"
    assert payload["version"] == "0.6.0"
    assert payload["validation"]["receipts"] == []
    assert payload["validation"]["environment_scope"] == "not_validated"
    assert payload["provenance"]["source"] == "live_discovery_unreviewed"
    assert payload["runtime"]["os_fallback"] == "operator_handoff_on_native_gap"
    assert payload["outputs"][0]["delivery"] == "artifact_only"
    assert {field["name"] for field in payload["outputs"][0]["fields"]} == {
        "sender",
        "displayed-date",
    }
    submit = next(
        milestone
        for milestone in payload["milestones"]
        if milestone["id"] == "submit-search"
    )
    postcondition = next(
        action for action in submit["actions"] if action["id"] == "press-gmail-search"
    )["postcondition"]
    assert postcondition["kind"] == "url_includes"
    assert postcondition["value"] == "#search/{{query}}"
    assert postcondition["locator_candidates"] == []
    assert {milestone["id"] for milestone in payload["milestones"]} >= {
        "open-gmail",
        "collect-results",
        "no-results",
        "search-transient",
    }
    serialized = json.dumps(payload)
    assert "@" not in serialized
    assert "message bodies" in serialized
    assert '"name": "subject"' not in serialized
    assert ".bog:visible" not in serialized


def test_agenzia_and_teamsystem_do_not_claim_unobserved_execution() -> None:
    for capability_id in ("agenzia-invoice-zip", "teamsystem-process"):
        payload = _capability(capability_id)

        assert payload["status"] == "scaffold"
        assert payload["validation"]["receipts"] == []
        assert payload["provenance"]["discovery_record_sha256"] is None
        assert all(milestone["actions"] == [] for milestone in payload["milestones"])
        assert any(
            "live discovery" in limit.lower()
            or "intentionally unresolved" in limit.lower()
            for limit in payload["validation"]["known_limits"]
        )


def test_contract_rejects_secret_fields_and_email_literals() -> None:
    contract = _load_contract()
    secret_payload = _capability("gmail-search-export")
    secret_payload["inputs"][0]["password"] = "not-allowed"
    email_payload = _capability("gmail-search-export")
    email_payload["inputs"][0]["purpose"] = "Use person@example.com"

    secret_errors = contract.validate_capability(secret_payload)
    email_errors = contract.validate_capability(email_payload)

    assert any("forbidden field 'password'" in error for error in secret_errors)
    assert any("contains an email address" in error for error in email_errors)


def test_contract_rejects_query_bearing_or_cross_origin_start_urls() -> None:
    contract = _load_contract()
    query_payload = _capability("gmail-search-export")
    query_payload["site"][
        "start_url"
    ] = "https://mail.google.com/mail/u/0/?account=private"
    cross_origin_payload = _capability("gmail-search-export")
    cross_origin_payload["site"]["start_url"] = "https://example.com/"

    query_errors = contract.validate_capability(query_payload)
    cross_origin_errors = contract.validate_capability(cross_origin_payload)

    assert any(
        "must not contain credentials, query, or fragment" in error
        for error in query_errors
    )
    assert any("must use an allowed origin" in error for error in cross_origin_errors)


def test_contract_requires_extension_model_and_playwright_runtime_split() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    payload["runtime"]["controller"] = "standalone_playwright"
    payload["runtime"]["semantic_driver"] = "rule_engine"

    errors = contract.validate_capability(payload)

    assert "runtime.controller must be 'chrome_extension'" in errors
    assert "runtime.semantic_driver must be 'model'" in errors


def test_contract_requires_semantic_locator_before_css_fallback() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    search_action = payload["milestones"][1]["actions"][1]
    search_action["locator_candidates"] = [
        {
            "kind": "css",
            "role": None,
            "value": "input[name=q]",
            "exact": True,
        }
    ]

    errors = contract.validate_capability(payload)

    assert any("requires at least one semantic locator" in error for error in errors)


def test_contract_requires_action_time_confirmation_for_consequential_action() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    action = payload["milestones"][1]["actions"][1]
    action["effect"] = "consequential"

    errors = contract.validate_capability(payload)

    assert any("confirmation must be 'action_time'" in error for error in errors)


def test_contract_rejects_unproven_validated_status() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    payload["status"] = "validated_local"

    errors = contract.validate_capability(payload)

    assert "validated_local requires two receipt references" in errors


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    (
        (("schema_version",), "browser-capability/v0", "schema_version must be"),
        (("capability_id",), "Bad ID", "capability_id must be"),
        (("version",), "one", "version must use"),
        (("status",), "proven", "status is unsupported"),
        (("site", "name"), "", "site.name must be"),
        (("site", "allowed_origins"), [], "allowed_origins must be"),
        (
            ("site", "allowed_origins", 0),
            "http://example.com",
            "must use HTTPS",
        ),
        (
            ("site", "allowed_origins", 0),
            "https://user:secret@example.com",
            "without embedded credentials",
        ),
        (
            ("site", "allowed_origins", 0),
            "https://example.com/private",
            "must not contain a path",
        ),
        (("site", "start_url"), "", "site.start_url must be"),
        (("process", "name"), "", "process.name must be"),
        (("process", "out_of_scope"), [""], "out_of_scope must contain"),
        (("inputs",), "invalid", "inputs must be an array"),
        (("inputs", 0, "name"), "Bad Name", "name must be a lower-case slug"),
        (("inputs", 0, "type"), "secret", "type is unsupported"),
        (("inputs", 0, "required"), "yes", "required must be boolean"),
        (("inputs", 0, "sensitivity"), "public", "sensitivity is unsupported"),
        (("inputs", 0, "purpose"), "", "purpose must be non-empty"),
        (("outputs",), [], "outputs must be a non-empty array"),
        (("outputs", 0, "name"), "Bad Name", "name must be a lower-case slug"),
        (("outputs", 0, "type"), "email", "type is unsupported"),
        (("outputs", 0, "description"), "", "description must be non-empty"),
        (("milestones",), [], "milestones must be a non-empty array"),
        (("milestones", 0, "id"), "Bad ID", "id must be a lower-case slug"),
        (("milestones", 0, "intent"), "", "intent must be non-empty"),
        (("milestones", 0, "preconditions"), [""], "preconditions must contain"),
        (("milestones", 0, "transitions"), [], "transitions must be non-empty"),
        (
            ("milestones", 0, "actions", 0, "id"),
            "Bad ID",
            "id must be a lower-case slug",
        ),
        (("milestones", 0, "actions", 0, "intent"), "", "intent must be non-empty"),
        (
            ("milestones", 0, "actions", 0, "operation"),
            "scroll",
            "operation is unsupported",
        ),
        (("milestones", 0, "actions", 0, "effect"), "write", "effect is unsupported"),
        (
            ("milestones", 0, "actions", 0, "path"),
            "relative",
            "query-free path",
        ),
        (("completion", "required_outputs"), [], "required_outputs must name"),
        (("completion", "terminal_milestones"), [], "terminal_milestones must name"),
        (("privacy", "model_data"), [], "model_data must contain"),
        (("privacy", "portable_artifact_excludes"), [], "is missing"),
        (("privacy", "private_evidence_retained"), True, "must be false"),
        (("validation", "environment_scope"), "global", "environment_scope must be"),
        (("validation", "known_limits"), [""], "known_limits must contain"),
        (("validation", "receipts"), "invalid", "receipts must be an array"),
        (
            ("validation", "execution_contract_sha256"),
            "bad",
            "unvalidated capability execution hash must be null",
        ),
        (("provenance", "source"), "recording", "draft provenance source must be"),
        (
            ("provenance", "portable_bundle_contains_private_evidence"),
            True,
            "portable bundles must not contain private discovery evidence",
        ),
    ),
)
def test_contract_reports_invalid_nested_capability_fields(
    path: tuple[object, ...], value: object, expected: str
) -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    _set_nested(payload, path, value)

    errors = contract.validate_capability(payload)

    assert any(expected in error for error in errors), errors


def test_contract_rejects_non_object_and_unsupported_top_level_field() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    payload["unsupported"] = True

    non_object_errors = contract.validate_capability([])
    extra_field_errors = contract.validate_capability(payload)

    assert non_object_errors == ["capability must be an object"]
    assert "capability has unsupported fields: unsupported" in extra_field_errors


def test_contract_rejects_duplicate_inputs_outputs_milestones_and_actions() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    payload["inputs"].append(copy.deepcopy(payload["inputs"][0]))
    payload["outputs"].append(copy.deepcopy(payload["outputs"][0]))
    payload["milestones"].append(copy.deepcopy(payload["milestones"][0]))

    errors = contract.validate_capability(payload)

    for expected in (
        "input names must be unique",
        "output names must be unique",
        "milestone ids must be unique",
        "action ids must be unique",
    ):
        assert expected in errors


def test_contract_rejects_invalid_locator_shapes_and_action_references() -> None:
    contract = _load_contract()
    payload = _capability("gmail-search-export")
    wait_action = payload["milestones"][0]["actions"][1]
    wait_action["locator_candidates"][0] = {
        "kind": "role",
        "role": None,
        "value": "Search mail",
        "exact": "yes",
    }
    fill_action = payload["milestones"][1]["actions"][0]
    fill_action["input_ref"] = "missing-input"
    press_action = payload["milestones"][1]["actions"][1]
    press_action["key"] = None

    errors = contract.validate_capability(payload)

    for expected in (
        "role is required for a role locator",
        "exact must be boolean",
        "input_ref must name an input",
        "key is required for press",
    ):
        assert any(expected in error for error in errors)


def test_discovery_contract_rejects_approval_without_review() -> None:
    contract = _load_contract()
    payload = {
        "schema_version": "browser-discovery/v2",
        "record_id": "synthetic-discovery",
        "recorded_at": "2026-08-24T18:00:00+02:00",
        "site": {
            "name": "Synthetic",
            "allowed_origins": ["https://example.com"],
            "start_url": "https://example.com/",
        },
        "process": {
            "name": "Synthetic process",
            "objective": "Prove the discovery validator.",
            "out_of_scope": [],
        },
        "runtime": copy.deepcopy(_capability("gmail-search-export")["runtime"]),
        "authority": copy.deepcopy(_capability("gmail-search-export")["authority"]),
        "privacy": copy.deepcopy(_capability("gmail-search-export")["privacy"]),
        "observations": [
            {
                "milestone_id": "open-page",
                "intent": "Find the synthetic control.",
                "origin": "https://example.com",
                "path": "/",
                "controls": [
                    {
                        "kind": "role",
                        "role": "button",
                        "value": "Continue",
                        "exact": True,
                    }
                ],
                "action": "Inspect the control.",
                "outcome": "The control is visible.",
                "uncertainties": [],
            }
        ],
        "branches": [],
        "downloads": [],
        "review": {
            "operator_reviewed": False,
            "approved_for_capability_authoring": True,
            "reviewed_at": None,
            "approval_id": None,
        },
    }

    errors = contract.validate_discovery_record(payload)

    assert "capability authoring approval requires operator review" in errors


def test_seal_writes_owner_only_deterministic_non_overwriting_bundle(
    tmp_path: Path,
) -> None:
    contract = _load_contract()
    helpers = _load_pipeline_test_helpers()
    discovery_payload = helpers._discovery(approved=True)
    discovery_path = helpers._write_json(tmp_path / "discovery.json", discovery_payload)
    draft_path = helpers._write_json(
        tmp_path / "draft.json", helpers._draft_for_discovery(discovery_payload)
    )
    source = tmp_path / "discovered.json"
    contract.promote_capability(draft_path, discovery_path, source)
    discovered = json.loads(source.read_text(encoding="utf-8"))
    receipt_paths = [
        helpers._write_run_evidence(
            tmp_path / "run-one",
            helpers._receipt(discovered, run_id="run-one"),
        ),
        helpers._write_run_evidence(
            tmp_path / "run-two",
            helpers._receipt(discovered, run_id="run-two"),
        ),
    ]
    validated = tmp_path / "validated.json"
    contract.finalize_capability(source, receipt_paths, validated)

    target = contract.seal_capability(
        validated, tmp_path / "bundle", discovery_path, receipt_paths
    )

    capability = target / "capability.json"
    lock = json.loads((target / "capability.lock.json").read_text(encoding="utf-8"))
    assert capability.read_bytes() == contract.canonical_json_bytes(
        json.loads(validated.read_text(encoding="utf-8"))
    )
    assert lock["capability_id"] == "gmail-search-export"
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    for path in target.rglob("*"):
        expected_mode = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected_mode
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        contract.seal_capability(
            validated, tmp_path / "bundle", discovery_path, receipt_paths
        )


def test_contract_cli_validates_all_checked_in_capabilities() -> None:
    for path in sorted(CAPABILITIES.glob("*/capability.json")):
        result = subprocess.run(
            [
                sys.executable,
                str(CONTRACT_PATH),
                "validate",
                str(path),
                "--kind",
                "capability",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "Capability contract is valid." in result.stderr


def test_checked_in_gmail_draft_excludes_obsolete_validation_bundle() -> None:
    bundle = CAPABILITIES / "gmail-search-export"

    assert not (bundle / "capability.lock.json").exists()
    assert not list((bundle / "receipts").glob("*.json"))
    assert not list((bundle / "run-locks").glob("*.json"))
    assert not (bundle / "outputs.json").exists()
    assert not (bundle / "browser-discovery.json").exists()


def test_contract_cli_reports_invalid_json(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid", encoding="utf-8")

    invalid_result = subprocess.run(
        [
            sys.executable,
            str(CONTRACT_PATH),
            "validate",
            str(invalid),
            "--kind",
            "capability",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert invalid_result.returncode == 1


def test_browser_automation_skill_is_generic_model_led_and_low_friction() -> None:
    skill = (COMPONENT / "skills" / "browser-automation" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(skill.split())

    for expected in (
        "chrome:control-chrome",
        "connected Chrome extension",
        "tab.playwright",
        "guided",
        "autonomous",
        "hybrid",
        "developer pack",
        "recoveryHandler",
        "Agenzia delle Entrate, TeamSystem, Gmail",
        "two distinct passed",
        "no Computer Use or desktop-control fallback",
        "native_gap",
        "capability_runtime.mjs",
        "capability_pipeline.py",
        "Never write run outputs inside this Git workspace",
    ):
        assert expected in normalized
    for retired in (
        "requirements-portal-recorder.txt",
        "record_agenzia_invoice_flow.py",
    ):
        assert retired not in skill
    assert "Do not ask the operator to say `visibile`" in skill
    assert "do not enumerate or inspect unrelated open tabs" in skill


def test_old_agenzia_recorder_runtime_is_removed() -> None:
    assert not (COMPONENT / "requirements-portal-recorder.txt").exists()
    assert not (COMPONENT / "scripts" / "record_agenzia_invoice_flow.py").exists()
    assert not (COMPONENT / "references" / "agenzia_invoice_flow_recording.md").exists()
    assert (COMPONENT / "scripts" / "capability_pipeline.py").is_file()
    assert (COMPONENT / "scripts" / "capability_runtime.mjs").is_file()
    assert (COMPONENT / "scripts" / "discovery_pack.py").is_file()
    assert (COMPONENT / "scripts" / "discovery_runtime.mjs").is_file()
    assert not (COMPONENT / "scripts" / "capability_contract.py").exists()


def test_core_dependency_check_needs_no_third_party_package() -> None:
    dependency_check = _load_dependency_check()

    result = dependency_check.main([])

    assert result == 0


def test_dependency_check_rejects_missing_requirement_file() -> None:
    dependency_check = _load_dependency_check()

    result = dependency_check.main(["--requirements", "missing.txt"])

    assert result == 1


def test_plugin_manifest_and_triggers_describe_generic_capability_authoring() -> None:
    manifest = json.loads(
        (COMPONENT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    evals = json.loads(
        (COMPONENT / "evals" / "trigger_fixtures.json").read_text(encoding="utf-8")
    )
    fixture_text = json.dumps(evals, ensure_ascii=False)

    assert manifest["version"] == "0.5.6"
    assert {
        "chrome-extension",
        "playwright",
        "teamsystem",
        "gmail",
        "gestionale",
    } <= set(manifest["keywords"])
    assert "computer-use" not in manifest["keywords"]
    assert "capability" in manifest["interface"]["longDescription"]
    assert "native_gap" in manifest["interface"]["longDescription"]
    assert (
        "controller desktop come fallback" in manifest["interface"]["longDescription"]
    )
    assert "TeamSystem" in fixture_text
    assert "capability portabile" in fixture_text
    assert "Agenzia delle Entrate" in fixture_text


def test_vera_wrapper_resolves_generic_module_without_managed_playwright() -> None:
    wrapper = (VERA / "skills" / "browser-automation" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "connected Chrome extension" in wrapper
    assert "no third-party dependency" in wrapper
    assert "Never look for runtime scripts inside this wrapper directory" in wrapper
    assert "no Computer Use or desktop-control fallback" in wrapper
    assert "native_gap" in wrapper
    assert "managed_python_runtime.py" not in wrapper
    assert "requirements-portal-recorder.txt" not in wrapper


def test_privacy_manifest_covers_live_control_metadata_and_portable_bundle() -> None:
    privacy = json.loads(
        (VERA / "privacy" / "workstreams" / "browser-automation.json").read_text(
            encoding="utf-8"
        )
    )
    classes = {item["id"]: item for item in privacy["model_context"]["classes"]}
    controls = {item["id"]: item for item in privacy["security_controls"]}
    boundary = privacy["external_boundaries"][0]

    assert "bounded-live-browser-process-discovery" in classes
    assert "sanitized-browser-discovery-developer-pack" in classes
    assert "portable-browser-process-capability" in classes
    assert "owner-only-browser-recovery-proposal" in classes
    assert "private-run-output-artifact" in classes
    assert (
        "selected control"
        in classes["bounded-live-browser-process-discovery"]["content"]
    )
    assert (
        "full authenticated-page snapshots"
        in classes["bounded-live-browser-process-discovery"]["content"]
    )
    assert "fresh task tab" in boundary["content"]
    boundary_controls = " ".join(boundary["controls"])
    assert "Do not use Computer Use" in boundary_controls
    assert "native_gap" in boundary_controls
    assert "reserves Computer Use" not in json.dumps(privacy, ensure_ascii=False)
    assert "environment-scoped-validation" in controls
    assert "separate-reviewed-developer-transfer" in controls
    assert "bounded-model-locator-recovery" in controls
    assert "reviewed-discovery-provenance" in controls
    assert "machine-generated-run-receipts" in controls
    assert "scaffolds-do-not-claim-live-support" in controls


def test_public_copy_discloses_live_model_data_and_portable_exclusions() -> None:
    copy_source = (ROOT / "static" / "shared" / "product-function-pages.js").read_text(
        encoding="utf-8"
    )

    for snippet in (
        '"browser-automation"',
        "process-specific",
        "connected Chrome session",
        "full authenticated-page snapshots",
        "separate confirmation",
        "discovery records",
        "account identifiers",
        "native_gap",
        "fallback desktop controller",
    ):
        assert snippet in copy_source
    assert "Only after the operator opens and reviews the file" not in copy_source


def test_cowork_projection_keeps_capability_review_but_blocks_live_claims() -> None:
    builder = (ROOT / "scripts" / "build_claude_plugin_zip.py").read_text(
        encoding="utf-8"
    )

    assert (
        "Live process discovery, execution, and validation require Codex Desktop"
        in builder
    )
    assert "inspect, explain, or edit a supplied sanitized developer pack" in builder
    assert "current Agenzia teaching recorder" not in builder
