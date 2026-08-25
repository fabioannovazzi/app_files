from __future__ import annotations

import copy
import hashlib
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
CAPABILITIES = COMPONENT / "capabilities"
PIPELINE_PATH = COMPONENT / "scripts" / "capability_pipeline.py"
DEPENDENCY_CHECK_PATH = COMPONENT / "scripts" / "check_dependencies.py"
RUNTIME_FIXTURE = ROOT / "tests" / "fixtures" / "browser_automation_runtime"


def _load_module(path: Path, name: str) -> ModuleType:
    """Load one dependency-free browser automation module."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pipeline() -> ModuleType:
    return _load_module(PIPELINE_PATH, "test_browser_capability_pipeline")


def _checked_in_capability(capability_id: str) -> dict[str, object]:
    path = CAPABILITIES / capability_id / "capability.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _capability(capability_id: str) -> dict[str, object]:
    """Return a draft fixture while preserving checked-in release evidence."""

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


def _discovery(*, approved: bool) -> dict[str, object]:
    gmail = _capability("gmail-search-export")
    return {
        "schema_version": "browser-discovery/v2",
        "record_id": "gmail-search-discovery",
        "recorded_at": "2026-08-24T18:00:00+02:00",
        "site": copy.deepcopy(gmail["site"]),
        "process": copy.deepcopy(gmail["process"]),
        "runtime": copy.deepcopy(gmail["runtime"]),
        "authority": copy.deepcopy(gmail["authority"]),
        "privacy": copy.deepcopy(gmail["privacy"]),
        "observations": [
            {
                "milestone_id": "open-gmail",
                "intent": "Observe the bounded Gmail entry state.",
                "origin": "https://mail.google.com",
                "path": "/mail/u/0/",
                "controls": [
                    {
                        "kind": "placeholder",
                        "role": None,
                        "value": "Search mail",
                        "exact": True,
                    }
                ],
                "action": "Open Gmail and wait for the search control.",
                "outcome": "The search control became visible.",
                "uncertainties": [],
            },
            {
                "milestone_id": "submit-search",
                "intent": "Observe the bounded search control.",
                "origin": "https://mail.google.com",
                "path": "/mail/u/0/",
                "controls": [
                    {
                        "kind": "placeholder",
                        "role": None,
                        "value": "Search mail",
                        "exact": True,
                    }
                ],
                "action": "Submit a no-result search expression.",
                "outcome": "The mailbox displayed its no-result state.",
                "uncertainties": ["Non-empty result-row locators remain provisional."],
            },
            {
                "milestone_id": "collect-results",
                "intent": "Observe the structured result-row boundary.",
                "origin": "https://mail.google.com",
                "path": "/mail/u/0/",
                "controls": [
                    {
                        "kind": "role",
                        "role": "main",
                        "value": None,
                        "exact": False,
                    }
                ],
                "action": "Inspect only the declared sender, subject, and displayed-date fields.",
                "outcome": "The bounded fields were available without opening a message.",
                "uncertainties": ["Repeated-row locators may vary by Gmail release."],
            },
            {
                "milestone_id": "no-results",
                "intent": "Observe the generic empty-result branch.",
                "origin": "https://mail.google.com",
                "path": "/mail/u/0/",
                "controls": [
                    {
                        "kind": "role",
                        "role": "main",
                        "value": None,
                        "exact": False,
                    }
                ],
                "action": "Inspect only the generic no-result marker.",
                "outcome": "The empty-result branch was distinguishable.",
                "uncertainties": ["Empty-state text may be localized."],
            },
        ],
        "branches": ["No-result and non-empty-result branches differ."],
        "downloads": [],
        "review": {
            "operator_reviewed": approved,
            "approved_for_capability_authoring": approved,
            "reviewed_at": "2026-08-24T18:30:00+02:00" if approved else None,
            "approval_id": "operator-review-one" if approved else None,
        },
    }


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _draft_for_discovery(discovery: dict[str, object]) -> dict[str, object]:
    pipeline = _pipeline()
    draft = _capability("gmail-search-export")
    draft["provenance"]["discovery_record_sha256"] = pipeline.sha256_payload(discovery)
    return draft


def _receipt(
    capability: dict[str, object], *, run_id: str, terminal: str = "collect-results"
) -> dict[str, object]:
    pipeline = _pipeline()
    output = capability["outputs"][0]
    completed = [capability["entry_milestone"], "submit-search", terminal]
    milestones = {item["id"]: item for item in capability["milestones"]}
    output_values = {
        "messages": (
            [
                {
                    "sender": "Synthetic sender",
                    "subject": "Synthetic subject",
                    "displayed-date": "2026-08-24",
                }
            ]
            if terminal == "collect-results"
            else []
        )
    }
    action_results = []
    for milestone_id in completed:
        for action in milestones[milestone_id]["actions"]:
            output_ref = action["output_ref"]
            output_value = output_values.get(output_ref) if output_ref else None
            locators = action["locator_candidates"]
            action_results.append(
                {
                    "milestone_id": milestone_id,
                    "action_id": action["id"],
                    "operation": action["operation"],
                    "result": "passed",
                    "started_at": "2026-08-24T19:00:00+02:00",
                    "finished_at": "2026-08-24T19:00:01+02:00",
                    "locator_candidate": (
                        {"index": 0, "kind": locators[0]["kind"]} if locators else None
                    ),
                    "origin": "https://mail.google.com",
                    "path": "/mail/u/0/",
                    "output_ref": output_ref,
                    "output_count": (
                        len(output_value) if output_value is not None else 0
                    ),
                    "output_sha256": (
                        pipeline.sha256_payload(output_value)
                        if output_value is not None
                        else None
                    ),
                    "error": None,
                }
            )
    return {
        "schema_version": "browser-run-receipt/v1",
        "runtime_version": "browser-capability-runtime/2",
        "run_id": run_id,
        "capability_id": capability["capability_id"],
        "capability_version": capability["version"],
        "execution_contract_sha256": pipeline.execution_contract_sha256(capability),
        "discovery_record_sha256": capability["provenance"]["discovery_record_sha256"],
        "started_at": "2026-08-24T19:00:00+02:00",
        "finished_at": "2026-08-24T19:00:01+02:00",
        "result": "passed",
        "entry_milestone": capability["entry_milestone"],
        "completed_milestones": completed,
        "terminal_milestone": terminal,
        "action_results": action_results,
        "outputs": [
            {
                "name": output["name"],
                "type": output["type"],
                "sensitivity": output["sensitivity"],
                "delivery": output["delivery"],
                "record_count": len(output_values["messages"]),
                "sha256": pipeline.sha256_payload(output_values["messages"]),
                "artifact": "outputs.json",
            }
        ],
        "input_hashes": {"query": "d" * 64, "max-results": "e" * 64},
        "locator_changes_during_run": False,
        "private_evidence_retained": False,
        "environment": {
            "browser": "existing_chrome",
            "controller": "chrome_extension",
            "origin_ui": "Gmail",
            "locale": "en",
        },
        "error": None,
    }


def _write_run_evidence(
    directory: Path,
    receipt: dict[str, object],
    *,
    terminal: str = "collect-results",
    outputs_override: dict[str, object] | None = None,
) -> Path:
    """Write canonical output, receipt, and lock files like the JS runtime."""

    pipeline = _pipeline()
    directory.mkdir()
    outputs = outputs_override or {
        "messages": (
            [
                {
                    "sender": "Synthetic sender",
                    "subject": "Synthetic subject",
                    "displayed-date": "2026-08-24",
                }
            ]
            if terminal == "collect-results"
            else []
        )
    }
    outputs_bytes = pipeline.canonical_json_bytes(outputs)
    receipt_bytes = pipeline.canonical_json_bytes(receipt)
    (directory / "outputs.json").write_bytes(outputs_bytes)
    receipt_path = directory / "run.receipt.json"
    receipt_path.write_bytes(receipt_bytes)
    run_lock = {
        "schema_version": "browser-run-lock/v1",
        "run_id": receipt["run_id"],
        "capability_id": receipt["capability_id"],
        "execution_contract_sha256": receipt["execution_contract_sha256"],
        "outputs_sha256": hashlib.sha256(outputs_bytes).hexdigest(),
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    (directory / "run.lock.json").write_bytes(pipeline.canonical_json_bytes(run_lock))
    return receipt_path


def _recovery_proposals(capability: dict[str, object]) -> dict[str, object]:
    pipeline = _pipeline()
    candidate = {
        "kind": "placeholder",
        "role": None,
        "value": "Find records",
        "exact": True,
    }
    return {
        "schema_version": "browser-recovery-proposals/v1",
        "runtime_version": "browser-capability-runtime/5",
        "run_id": "recovered-run",
        "capability_id": capability["capability_id"],
        "capability_version": capability["version"],
        "execution_contract_sha256": pipeline.execution_contract_sha256(capability),
        "discovery_record_sha256": capability["provenance"]["discovery_record_sha256"],
        "proposals": [
            {
                "sequence": 1,
                "milestone_id": "submit-search",
                "action_id": "fill-gmail-search",
                "action_intent": "Fill the declared search control.",
                "operation": "fill",
                "effect": "reversible",
                "origin": "https://mail.google.com",
                "path": "/mail/u/0/",
                "original_locator_candidates_sha256": "b" * 64,
                "candidate_index": 1,
                "candidate": candidate,
                "candidate_sha256": pipeline.sha256_payload(candidate),
                "rationale": "The accessible placeholder changed for this run.",
                "uncertainty": "The locator remains provisional until reviewed.",
                "original_failure": {
                    "code": "locator_not_found",
                    "detail_sha256": "c" * 64,
                },
                "outcome": "passed",
                "outcome_error": None,
                "approved_for_persistence": False,
            }
        ],
        "portable": False,
        "requires_operator_review_before_persistence": True,
    }


def test_checked_in_capabilities_are_v2_and_honest() -> None:
    pipeline = _pipeline()
    expected = {
        "agenzia-invoice-zip": "scaffold",
        "gmail-search-export": "validated_local",
        "teamsystem-process": "scaffold",
    }

    actual = {}
    for capability_id, status in expected.items():
        payload = _checked_in_capability(capability_id)
        actual[capability_id] = payload["status"]
        assert payload["schema_version"] == "browser-capability/v2"
        assert pipeline.validate_capability(payload) == []

    assert actual == expected
    assert sorted(
        path.parent.name for path in CAPABILITIES.glob("*/capability.json")
    ) == sorted(expected)


def test_synthetic_fixture_discovery_reproduces_discovered_capability(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovered = json.loads(
        (RUNTIME_FIXTURE / "capability.json").read_text(encoding="utf-8")
    )
    discovery_path = RUNTIME_FIXTURE / "discovery.json"
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    draft = copy.deepcopy(discovered)
    draft["status"] = "draft"
    draft["provenance"] = {
        "source": "live_discovery_unreviewed",
        "discovery_record_sha256": pipeline.sha256_payload(discovery),
        "discovery_approval_id": None,
        "discovery_approved_at": None,
        "portable_bundle_contains_private_evidence": False,
    }
    output_path = tmp_path / "discovered.json"

    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft), discovery_path, output_path
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == discovered


def test_scaffolds_do_not_claim_unobserved_execution() -> None:
    for capability_id in ("agenzia-invoice-zip", "teamsystem-process"):
        payload = _capability(capability_id)
        assert payload["validation"]["receipts"] == []
        assert payload["provenance"]["discovery_record_sha256"] is None
        assert all(milestone["actions"] == [] for milestone in payload["milestones"])


def test_gmail_capability_is_useful_and_locally_validated() -> None:
    payload = _checked_in_capability("gmail-search-export")

    assert payload["status"] == "validated_local"
    assert payload["outputs"][0]["fields"] == [
        {"name": "sender", "type": "text", "required": True},
        {"name": "subject", "type": "text", "required": True},
        {"name": "displayed-date", "type": "text", "required": False},
    ]
    assert {item["id"] for item in payload["milestones"]} >= {
        "collect-results",
        "no-results",
    }
    assert payload["outputs"][0]["delivery"] == "artifact_only"
    assert payload["validation"]["environment_scope"] == "existing_chrome_origin_ui"
    assert len(payload["validation"]["receipts"]) == 2
    assert payload["provenance"]["source"] == "authorized_live_discovery"


def test_validator_rejects_secrets_email_literals_and_cross_origin_urls() -> None:
    pipeline = _pipeline()
    secret = _capability("gmail-search-export")
    secret["inputs"][0]["password"] = "not-allowed"
    email = _capability("gmail-search-export")
    email["inputs"][0]["purpose"] = "Use person@example.com"
    query = _capability("gmail-search-export")
    query["site"]["start_url"] += "?account=private"
    cross_origin = _capability("gmail-search-export")
    cross_origin["site"]["start_url"] = "https://example.com/"

    assert any(
        "forbidden field 'password'" in item
        for item in pipeline.validate_capability(secret)
    )
    assert any(
        "contains an email address" in item
        for item in pipeline.validate_capability(email)
    )
    assert any(
        "query, or fragment" in item for item in pipeline.validate_capability(query)
    )
    assert any(
        "allowed origin" in item for item in pipeline.validate_capability(cross_origin)
    )


def test_validator_enforces_runtime_semantics_and_action_confirmation() -> None:
    pipeline = _pipeline()
    runtime = _capability("gmail-search-export")
    runtime["runtime"]["controller"] = "standalone_playwright"
    runtime["runtime"]["semantic_driver"] = "rule_engine"
    locator = _capability("gmail-search-export")
    locator["milestones"][0]["actions"][1]["locator_candidates"] = [
        {"kind": "css", "role": None, "value": "input", "exact": False}
    ]
    action = _capability("gmail-search-export")
    action["milestones"][1]["actions"][1]["effect"] = "consequential"

    runtime_errors = pipeline.validate_capability(runtime)
    assert "runtime.controller must be 'chrome_extension'" in runtime_errors
    assert "runtime.semantic_driver must be 'model'" in runtime_errors
    assert any(
        "semantic locator" in item for item in pipeline.validate_capability(locator)
    )
    assert any(
        "confirmation must be 'action_time'" in item
        for item in pipeline.validate_capability(action)
    )


def test_validator_allows_visible_structural_css_for_transition_state() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")

    errors = pipeline.validate_capability(capability)

    assert errors == []


def test_validator_rejects_unscoped_css_only_transition_state() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    transition = capability["milestones"][1]["transitions"][0]["when"]
    transition["locator_candidates"][0]["value"] = "tr.zA"

    errors = pipeline.validate_capability(capability)

    assert any("requires at least one semantic locator" in item for item in errors)


def test_validator_limits_model_summary_delivery_to_summary_outputs() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    capability["outputs"][0]["delivery"] = "model_summary"

    errors = pipeline.validate_capability(capability)

    assert any(
        "model_summary delivery requires scalar or summary type" in item
        for item in errors
    )


def test_validator_keeps_download_paths_out_of_model_delivery() -> None:
    pipeline = _pipeline()
    capability = _capability("agenzia-invoice-zip")
    capability["outputs"][0]["delivery"] = "model_and_artifact"

    errors = pipeline.validate_capability(capability)

    assert "outputs[0].download_set delivery must be artifact_only" in errors


def test_recovery_proposal_validator_accepts_only_bounded_semantic_changes() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    recovery = _recovery_proposals(capability)

    assert pipeline.validate_recovery_proposals(recovery) == []

    recovery["proposals"][0]["effect"] = "consequential"
    recovery["proposals"][0]["candidate"] = {
        "kind": "css",
        "role": None,
        "value": "input.search",
        "exact": False,
    }
    recovery["portable"] = True

    errors = pipeline.validate_recovery_proposals(recovery)

    assert any("effect is not recoverable" in item for item in errors)
    assert any("candidate must be semantic" in item for item in errors)
    assert "recovery.portable must be false" in errors


def test_recovery_run_lock_hashes_the_owner_only_proposal() -> None:
    pipeline = _pipeline()
    recovery = _recovery_proposals(_capability("gmail-search-export"))
    lock = {
        "schema_version": "browser-run-lock/v2",
        "run_id": recovery["run_id"],
        "capability_id": recovery["capability_id"],
        "execution_contract_sha256": recovery["execution_contract_sha256"],
        "outputs_sha256": "d" * 64,
        "receipt_sha256": "e" * 64,
        "recovery_proposals_sha256": pipeline.sha256_payload(recovery),
    }

    assert pipeline.validate_run_lock(lock) == []

    lock["recovery_proposals_sha256"] = "not-a-hash"
    assert (
        "run_lock.recovery_proposals_sha256 must be a SHA-256"
        in pipeline.validate_run_lock(lock)
    )


def test_validator_requires_an_executable_producer_for_required_outputs() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    capability["outputs"].append(
        {
            "name": "unproduced-summary",
            "type": "summary",
            "sensitivity": "non_sensitive",
            "delivery": "artifact_only",
            "description": "An intentionally unproduced test output.",
            "fields": [],
        }
    )
    capability["completion"]["required_outputs"].append("unproduced-summary")

    errors = pipeline.validate_capability(capability)

    assert "required outputs have no executable producer: unproduced-summary" in errors


def test_validator_accepts_text_extraction_for_summary_output() -> None:
    pipeline = _pipeline()
    capability = json.loads(
        (RUNTIME_FIXTURE / "capability.json").read_text(encoding="utf-8")
    )
    capability["outputs"] = [
        {
            "name": "status-summary",
            "type": "summary",
            "sensitivity": "non_sensitive",
            "delivery": "model_summary",
            "description": "Visible fixture status.",
            "fields": [],
        }
    ]
    capability["milestones"] = [
        milestone
        for milestone in capability["milestones"]
        if milestone["id"] != "no-results"
    ]
    submit = capability["milestones"][1]
    submit["transitions"] = [submit["transitions"][1]]
    extraction = capability["milestones"][2]["actions"][0]
    extraction["output_ref"] = "status-summary"
    extraction["locator_candidates"] = [
        {"kind": "role", "role": "status", "value": None, "exact": False}
    ]
    extraction["extract"] = {
        "mode": "text",
        "fields": [],
        "max_items": 1,
        "limit_input_ref": None,
        "empty_allowed": False,
        "dedupe_by": [],
    }
    extraction["postcondition"] = {
        "kind": "output_nonempty",
        "locator_candidates": [],
        "value": None,
        "output_ref": "status-summary",
        "comparator": None,
        "expected": None,
        "timeout_ms": 10_000,
    }
    capability["milestones"][2]["transitions"][0]["when"][
        "output_ref"
    ] = "status-summary"
    capability["completion"] = {
        "terminal_milestones": ["collect-results"],
        "required_outputs": ["status-summary"],
    }

    errors = pipeline.validate_capability(capability)

    assert errors == []


def test_validator_requires_exact_output_fields_and_numeric_list_limit() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    extraction = capability["milestones"][2]["actions"][0]["extract"]
    extraction["fields"] = extraction["fields"][:-1]
    extraction["limit_input_ref"] = "query"

    errors = pipeline.validate_capability(capability)

    assert any("fields must exactly cover the output fields" in item for item in errors)
    assert any("limit_input_ref must name a number input" in item for item in errors)


def test_validator_rejects_unreachable_and_inconsistent_terminal_graphs() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    orphan = copy.deepcopy(capability["milestones"][-1])
    orphan["id"] = "orphan-terminal"
    orphan["actions"][0]["id"] = "verify-orphan"
    capability["milestones"].append(orphan)
    capability["completion"]["terminal_milestones"] = ["collect-results"]

    errors = pipeline.validate_capability(capability)

    assert any("unreachable milestones: orphan-terminal" in item for item in errors)
    assert "completion terminal milestones do not match terminal transitions" in errors


def test_validator_rejects_unreachable_transition_order_and_terminal_cycles() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    submit = capability["milestones"][1]
    submit["transitions"].insert(
        0,
        {
            "when": {
                "kind": "always",
                "locator_candidates": [],
                "value": None,
                "output_ref": None,
                "comparator": None,
                "expected": None,
                "timeout_ms": 10_000,
            },
            "next_milestone": "no-results",
            "terminal": False,
        },
    )
    no_results = capability["milestones"][3]
    no_results["transitions"] = [
        {
            "when": {
                "kind": "always",
                "locator_candidates": [],
                "value": None,
                "output_ref": None,
                "comparator": None,
                "expected": None,
                "timeout_ms": 10_000,
            },
            "next_milestone": "no-results",
            "terminal": False,
        }
    ]

    errors = pipeline.validate_capability(capability)

    assert "milestone submit-search unconditional transition must be last" in errors
    assert "milestones cannot reach a terminal: no-results" in errors


def test_validator_matches_extraction_mode_to_output_cardinality() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    extraction = capability["milestones"][2]["actions"][0]["extract"]
    extraction["mode"] = "single"

    errors = pipeline.validate_capability(capability)

    assert any("mode must be 'list' for record_set output" in item for item in errors)
    assert any("max_items must be 1 for single mode" in item for item in errors)
    assert any(
        "limit_input_ref must be null for single mode" in item for item in errors
    )


def test_validator_requires_nonempty_outputs_on_every_terminal_path() -> None:
    pipeline = _pipeline()
    capability = _capability("gmail-search-export")
    capability["outputs"].append(
        {
            "name": "status-summary",
            "type": "summary",
            "sensitivity": "non_sensitive",
            "delivery": "model_summary",
            "description": "Visible search status.",
            "fields": [],
        }
    )
    capability["completion"]["required_outputs"].append("status-summary")
    capability["milestones"][2]["actions"].append(
        {
            "id": "extract-status-summary",
            "intent": "Extract the visible result status.",
            "operation": "extract",
            "effect": "read_only",
            "confirmation": "none",
            "locator_candidates": [
                {"kind": "role", "role": "main", "value": None, "exact": False}
            ],
            "input_ref": None,
            "key": None,
            "path": None,
            "target_origin": None,
            "output_ref": "status-summary",
            "extract": {
                "mode": "text",
                "fields": [],
                "max_items": 1,
                "limit_input_ref": None,
                "empty_allowed": False,
                "dedupe_by": [],
            },
            "postcondition": {
                "kind": "output_nonempty",
                "locator_candidates": [],
                "value": None,
                "output_ref": "status-summary",
                "comparator": None,
                "expected": None,
                "timeout_ms": 10_000,
            },
            "timeout_ms": 10_000,
        }
    )

    errors = pipeline.validate_capability(capability)

    assert (
        "terminal no-results can finish without required outputs: status-summary"
        in errors
    )


def test_discovery_approval_gate_fails_closed_and_promotes_exact_record(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    unapproved = _discovery(approved=False)
    draft = _draft_for_discovery(unapproved)
    draft_path = _write_json(tmp_path / "draft.json", draft)
    discovery_path = _write_json(tmp_path / "discovery.json", unapproved)

    with pytest.raises(ValueError, match="not been reviewed"):
        pipeline.promote_capability(
            draft_path, discovery_path, tmp_path / "discovered.json"
        )

    approved = _discovery(approved=True)
    approved_draft = _draft_for_discovery(approved)
    approved_draft_path = _write_json(tmp_path / "approved-draft.json", approved_draft)
    approved_path = _write_json(tmp_path / "approved-discovery.json", approved)
    output_path = tmp_path / "promoted.json"
    pipeline.promote_capability(approved_draft_path, approved_path, output_path)
    promoted = json.loads(output_path.read_text(encoding="utf-8"))

    assert promoted["status"] == "discovered"
    assert promoted["provenance"]["source"] == "authorized_live_discovery"
    assert promoted["provenance"]["discovery_approval_id"] == "operator-review-one"
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600


def test_promotion_rejects_a_different_reviewed_record(tmp_path: Path) -> None:
    pipeline = _pipeline()
    approved = _discovery(approved=True)
    draft = _draft_for_discovery(approved)
    changed = copy.deepcopy(approved)
    changed["branches"].append("Changed after drafting.")

    with pytest.raises(ValueError, match="hash does not match"):
        pipeline.promote_capability(
            _write_json(tmp_path / "draft.json", draft),
            _write_json(tmp_path / "changed.json", changed),
            tmp_path / "output.json",
        )


def test_promotion_rejects_broader_process_or_unobserved_milestones(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    narrower_discovery = _discovery(approved=True)
    narrower_discovery["process"]["name"] = "Synthetic no-result proof"
    broader_draft = _capability("gmail-search-export")
    broader_draft["provenance"]["discovery_record_sha256"] = pipeline.sha256_payload(
        narrower_discovery
    )
    with pytest.raises(ValueError, match="draft process does not match"):
        pipeline.promote_capability(
            _write_json(tmp_path / "broader-draft.json", broader_draft),
            _write_json(tmp_path / "narrower-discovery.json", narrower_discovery),
            tmp_path / "broader-output.json",
        )

    incomplete_discovery = _discovery(approved=True)
    incomplete_discovery["observations"] = incomplete_discovery["observations"][:-1]
    incomplete_draft = _draft_for_discovery(incomplete_discovery)
    with pytest.raises(ValueError, match="does not cover executable milestones"):
        pipeline.promote_capability(
            _write_json(tmp_path / "incomplete-draft.json", incomplete_draft),
            _write_json(tmp_path / "incomplete-discovery.json", incomplete_discovery),
            tmp_path / "incomplete-output.json",
        )


def test_model_recovery_receipts_cannot_count_as_clean_validation(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    capability = json.loads(discovered_path.read_text(encoding="utf-8"))
    receipts = []
    for index in (1, 2):
        receipt = _receipt(capability, run_id=f"recovered-run-{index}")
        receipt["locator_changes_during_run"] = True
        receipts.append(_write_run_evidence(tmp_path / f"recovered-{index}", receipt))

    with pytest.raises(ValueError, match="used model recovery"):
        pipeline.finalize_capability(
            discovered_path,
            receipts,
            tmp_path / "validated.json",
        )


def test_two_machine_receipts_finalize_and_seal_a_reviewed_capability(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    draft_path = _write_json(tmp_path / "draft.json", draft)
    discovery_path = _write_json(tmp_path / "discovery.json", discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(draft_path, discovery_path, discovered_path)
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    receipt_one = _receipt(discovered, run_id="clean-run-one")
    receipt_two = _receipt(discovered, run_id="clean-run-two", terminal="no-results")
    receipt_paths = [
        _write_run_evidence(tmp_path / "run-one", receipt_one),
        _write_run_evidence(tmp_path / "run-two", receipt_two, terminal="no-results"),
    ]
    validated_path = tmp_path / "validated.json"

    pipeline.finalize_capability(discovered_path, receipt_paths, validated_path)
    validated = json.loads(validated_path.read_text(encoding="utf-8"))
    bundle = pipeline.seal_capability(
        validated_path, tmp_path / "handoff", discovery_path, receipt_paths
    )

    assert validated["status"] == "validated_local"
    assert len(validated["validation"]["receipts"]) == 2
    assert pipeline.verify_bundle(bundle) == []
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in bundle.rglob("*")
        if path.is_file()
    )
    lock = json.loads((bundle / "capability.lock.json").read_text(encoding="utf-8"))
    assert "README.md" in lock["files"]
    assert len(list((bundle / "run-locks").glob("*.json"))) == 2
    assert not (bundle / "browser-discovery.json").exists()
    assert not (bundle / "outputs.json").exists()


def test_finalizer_rejects_duplicate_or_tampered_receipts(tmp_path: Path) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    receipt = _receipt(discovered, run_id="same-run")
    first = _write_run_evidence(tmp_path / "first", receipt)
    second = _write_run_evidence(tmp_path / "second", receipt)

    with pytest.raises(ValueError, match="unique run ids"):
        pipeline.finalize_capability(
            discovered_path, [first, second], tmp_path / "duplicate.json"
        )

    tampered = _receipt(discovered, run_id="other-run")
    tampered["execution_contract_sha256"] = "f" * 64
    tampered_path = _write_run_evidence(tmp_path / "tampered", tampered)
    with pytest.raises(ValueError, match="execution hash does not match"):
        pipeline.finalize_capability(
            discovered_path,
            [first, tampered_path],
            tmp_path / "tampered-output.json",
        )


def test_finalizer_rejects_output_changed_after_runtime(tmp_path: Path) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    first = _write_run_evidence(
        tmp_path / "run-one", _receipt(discovered, run_id="linked-run-one")
    )
    second = _write_run_evidence(
        tmp_path / "run-two", _receipt(discovered, run_id="linked-run-two")
    )
    changed_outputs = {"messages": []}
    (first.parent / "outputs.json").write_bytes(
        pipeline.canonical_json_bytes(changed_outputs)
    )

    with pytest.raises(ValueError, match="run lock output hash does not match"):
        pipeline.finalize_capability(
            discovered_path, [first, second], tmp_path / "validated.json"
        )


def test_finalizer_rejects_hash_consistent_output_with_wrong_field_type(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    wrong_outputs = {
        "messages": [
            {
                "sender": 42,
                "subject": "Synthetic subject",
                "displayed-date": "2026-08-24",
            }
        ]
    }
    wrong_receipt = _receipt(discovered, run_id="wrong-output-type")
    wrong_receipt["outputs"][0]["sha256"] = pipeline.sha256_payload(
        wrong_outputs["messages"]
    )
    wrong = _write_run_evidence(
        tmp_path / "wrong-output",
        wrong_receipt,
        outputs_override=wrong_outputs,
    )
    valid = _write_run_evidence(
        tmp_path / "valid-output", _receipt(discovered, run_id="valid-output-type")
    )

    with pytest.raises(ValueError, match=r"outputs.messages\[0\].sender must be text"):
        pipeline.finalize_capability(
            discovered_path, [wrong, valid], tmp_path / "validated.json"
        )


def test_finalizer_rejects_hash_consistent_action_outside_allowed_origin(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    wrong_receipt = _receipt(discovered, run_id="wrong-action-origin")
    wrong_receipt["action_results"][0]["origin"] = "https://example.com"
    wrong = _write_run_evidence(tmp_path / "wrong-origin", wrong_receipt)
    valid = _write_run_evidence(
        tmp_path / "valid-origin", _receipt(discovered, run_id="valid-action-origin")
    )

    with pytest.raises(ValueError, match="action origin is outside capability"):
        pipeline.finalize_capability(
            discovered_path, [wrong, valid], tmp_path / "validated.json"
        )


def test_finalizer_rejects_hash_consistent_output_declaration_mismatch(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    wrong_receipt = _receipt(discovered, run_id="wrong-output-declaration")
    wrong_receipt["outputs"][0]["delivery"] = "model_and_artifact"
    wrong = _write_run_evidence(tmp_path / "wrong-declaration", wrong_receipt)
    valid = _write_run_evidence(
        tmp_path / "valid-declaration",
        _receipt(discovered, run_id="valid-output-declaration"),
    )

    with pytest.raises(ValueError, match="output declaration does not match"):
        pipeline.finalize_capability(
            discovered_path, [wrong, valid], tmp_path / "validated.json"
        )


def test_finalizer_rejects_hash_consistent_missing_required_input(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft),
        _write_json(tmp_path / "discovery.json", discovery),
        discovered_path,
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    wrong_receipt = _receipt(discovered, run_id="missing-required-input")
    wrong_receipt["input_hashes"].pop("max-results")
    wrong = _write_run_evidence(tmp_path / "missing-input", wrong_receipt)
    valid = _write_run_evidence(
        tmp_path / "valid-input", _receipt(discovered, run_id="valid-input")
    )

    with pytest.raises(ValueError, match="missing required input hashes"):
        pipeline.finalize_capability(
            discovered_path, [wrong, valid], tmp_path / "validated.json"
        )


def test_bundle_verifier_detects_tampering_and_unlisted_files(tmp_path: Path) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovered_path = tmp_path / "discovered.json"
    discovery_path = _write_json(tmp_path / "discovery.json", discovery)
    pipeline.promote_capability(
        _write_json(tmp_path / "draft.json", draft), discovery_path, discovered_path
    )
    bundle = pipeline.seal_capability(
        discovered_path, tmp_path / "handoff", discovery_path
    )
    (bundle / "README.md").write_text("tampered", encoding="utf-8")
    (bundle / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    errors = pipeline.verify_bundle(bundle)

    assert "bundle file hash mismatch: README.md" in errors
    assert "bundle contains unlisted file: unexpected.txt" in errors


def test_receipt_validator_rejects_false_success_and_raw_error_detail() -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    capability = _draft_for_discovery(discovery)
    capability["status"] = "discovered"
    capability["provenance"] = {
        "source": "authorized_live_discovery",
        "discovery_record_sha256": pipeline.sha256_payload(discovery),
        "discovery_approval_id": "operator-review-one",
        "discovery_approved_at": "2026-08-24T18:30:00+02:00",
        "portable_bundle_contains_private_evidence": False,
    }
    receipt = _receipt(capability, run_id="false-success")
    receipt["terminal_milestone"] = None
    receipt["action_results"][0]["result"] = "failed"
    receipt["action_results"][0]["error"] = {"message": "private raw detail"}

    errors = pipeline.validate_run_receipt(receipt)

    assert "passed receipt requires a terminal milestone" in errors
    assert "passed receipt must not contain failed actions" in errors
    assert any("unsupported fields: message" in item for item in errors)


def test_cli_validates_all_checked_in_capabilities_and_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    for path in sorted(CAPABILITIES.glob("*/capability.json")):
        result = subprocess.run(
            [
                sys.executable,
                str(PIPELINE_PATH),
                "validate",
                "--kind",
                "capability",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "Capability contract is valid." in result.stderr

    invalid = _write_json(tmp_path / "invalid.json", [])
    invalid_result = subprocess.run(
        [
            sys.executable,
            str(PIPELINE_PATH),
            "validate",
            "--kind",
            "capability",
            str(invalid),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid_result.returncode == 1


def test_direct_cli_runs_reviewed_lifecycle_and_all_evidence_validators(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline()
    discovery = _discovery(approved=True)
    draft = _draft_for_discovery(discovery)
    discovery_path = _write_json(tmp_path / "discovery.json", discovery)
    draft_path = _write_json(tmp_path / "draft.json", draft)
    discovered_path = tmp_path / "discovered.json"

    assert pipeline.main(["validate", str(draft_path), "--kind", "capability"]) == 0
    assert pipeline.main(["validate", str(discovery_path), "--kind", "discovery"]) == 0
    assert (
        pipeline.main(
            [
                "promote",
                str(draft_path),
                "--discovery-record",
                str(discovery_path),
                "--output",
                str(discovered_path),
            ]
        )
        == 0
    )
    discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
    receipt_paths = [
        _write_run_evidence(
            tmp_path / "run-one", _receipt(discovered, run_id="cli-run-one")
        ),
        _write_run_evidence(
            tmp_path / "run-two",
            _receipt(discovered, run_id="cli-run-two", terminal="no-results"),
            terminal="no-results",
        ),
    ]
    assert pipeline.main(["validate", str(receipt_paths[0]), "--kind", "receipt"]) == 0
    assert (
        pipeline.main(
            [
                "validate",
                str(receipt_paths[0].with_name("run.lock.json")),
                "--kind",
                "run-lock",
            ]
        )
        == 0
    )
    validated_path = tmp_path / "validated.json"
    assert (
        pipeline.main(
            [
                "finalize",
                str(discovered_path),
                "--receipt",
                str(receipt_paths[0]),
                "--receipt",
                str(receipt_paths[1]),
                "--output",
                str(validated_path),
            ]
        )
        == 0
    )
    handoff = tmp_path / "handoff"
    assert (
        pipeline.main(
            [
                "seal",
                str(validated_path),
                "--discovery-record",
                str(discovery_path),
                "--receipt",
                str(receipt_paths[0]),
                "--receipt",
                str(receipt_paths[1]),
                "--output-directory",
                str(handoff),
            ]
        )
        == 0
    )
    bundle = handoff / "gmail-search-export"
    assert pipeline.main(["verify-bundle", str(bundle)]) == 0
    assert pipeline.main(["verify-bundle", str(tmp_path / "missing")]) == 1


def test_core_dependency_check_needs_no_third_party_package() -> None:
    dependency_check = _load_module(
        DEPENDENCY_CHECK_PATH, "test_browser_dependency_check"
    )

    assert dependency_check.main([]) == 0
    assert dependency_check.main(["--requirements", "missing.txt"]) == 1
