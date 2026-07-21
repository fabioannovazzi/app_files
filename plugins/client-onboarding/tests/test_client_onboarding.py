from __future__ import annotations

import copy
import json
import shutil
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import check_dependencies as dependency_check
import onboarding_core
from initialize_case import build_template, initialize_case
from onboarding_core import (
    AML_A_FACTOR_IDS,
    AML_B_FACTOR_IDS,
    AML_TRIGGER_IDS,
    EXPECTED_ARTIFACTS,
    ValidationError,
    add_months_clamped,
    build_monitoring_plan,
    calculate_aml,
    canonical_json_hash,
    ensure_private_output_directory,
    load_json,
    load_source_registry,
    sha256_file,
    validate_contract,
    validate_intake,
)
from package_onboarding import package_onboarding

from scripts.validate_plugin_review_contract import (
    validate_contract as validate_shared_review_contract,
)

PROFESSIONAL_CONFIRMED_AT = "2026-01-31T10:00:00+01:00"


def test_dependency_checker_reports_ready(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = dependency_check.main([])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "ready"
    assert report["dependencies"] == "python_standard_library_only"
    assert report["issues"] == []


def _evidence(evidence_id: str, local_path: Path) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "evidence_type": "verified_record",
        "status": "verified",
        "obtained_on": "2026-01-31",
        "expires_on": None,
        "sha256": sha256_file(local_path),
        "local_path": local_path.as_posix(),
    }


def _verified_identity(evidence_id: str, document_number: str) -> dict[str, Any]:
    return {
        "verification_status": "verified",
        "document_type": "identity_card",
        "document_number": document_number,
        "issuer": "Recorded issuing authority",
        "issued_on": "2024-01-31",
        "expires_on": "2034-01-31",
        "verified_on": "2026-01-31",
        "verification_method": "document_and_presence_check",
        "evidence_ids": [evidence_id],
    }


def _set_aml_scores(
    payload: dict[str, Any],
    score: int | float,
    *,
    status: str = "confirmed",
) -> None:
    payload["aml"]["inherent_risk"] = score
    payload["aml"]["inherent_risk_status"] = status
    for factor in [*payload["aml"]["factors_a"], *payload["aml"]["factors_b"]]:
        factor["score"] = score
        factor["assessment_status"] = status
        if status == "confirmed":
            factor["confirmed_by_role"] = "professional"
            factor["confirmed_at"] = PROFESSIONAL_CONFIRMED_AT
        else:
            factor.pop("confirmed_by_role", None)
            factor.pop("confirmed_at", None)


def _confirm_negative_triggers(payload: dict[str, Any]) -> None:
    for trigger in payload["aml"]["mandatory_enhanced_triggers"]:
        trigger["status"] = "no"
        trigger["review_status"] = "confirmed"
        trigger["basis"] = "Professional negative finding recorded."
        trigger["confirmed_by_role"] = "professional"
        trigger["confirmed_at"] = PROFESSIONAL_CONFIRMED_AT


def _confirm_table_1(payload: dict[str, Any], *, status: str = "no") -> None:
    payload["aml"]["table_1_assessment"] = {
        "status": status,
        "review_status": "confirmed",
        "basis": "Professional Table 1 applicability basis recorded.",
        "confirmed_by_role": "professional",
        "confirmed_at": PROFESSIONAL_CONFIRMED_AT,
    }


def _complete_intake(tmp_path: Path) -> dict[str, Any]:
    payload = build_template(
        "CASE-ALPHA",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    evidence_dir = tmp_path / "case-evidence"
    evidence_dir.mkdir(parents=True)
    identity_evidence_ids = (
        "ev-cf",
        "ev-piva",
        "ev-party-id",
        "ev-rep-1",
        "ev-rep-2",
        "ev-owner-1",
        "ev-owner-2",
    )
    subjects = (
        "CASE-ALPHA",
        "REP-EXECUTOR-01",
        "REP-LEGAL-02",
        "OWNER-01",
        "OWNER-02",
    )
    screening_evidence_ids = {
        (subject, screening_type): (f"ev-screen-{subject.casefold()}-{screening_type}")
        for subject in subjects
        for screening_type in ("pep", "sanctions", "country")
    }
    all_evidence_ids = [*identity_evidence_ids, *screening_evidence_ids.values()]
    evidence_paths: dict[str, Path] = {}
    for evidence_id in all_evidence_ids:
        path = evidence_dir / f"{evidence_id}.txt"
        path.write_text(f"verified evidence for {evidence_id}\n", encoding="utf-8")
        evidence_paths[evidence_id] = path
    payload["evidence_register"] = [
        _evidence(evidence_id, path) for evidence_id, path in evidence_paths.items()
    ]
    payload["tax_facts"] = {
        "codice_fiscale": {
            "value": "RSSMRA80A01H501U",
            "verification_status": "verified",
            "evidence_ids": ["ev-cf"],
        },
        "partita_iva": {
            "value": "01234567890",
            "verification_status": "verified",
            "evidence_ids": ["ev-piva"],
        },
    }
    payload["party_facts"] = [
        {
            "fact_id": "party-fact-01",
            "fact_code": "registered_identity",
            "value": "Sensitive registered identity",
            "verification_status": "verified",
            "evidence_ids": ["ev-party-id"],
        },
        {
            "fact_id": "party-fact-02",
            "fact_code": "economic_profile",
            "value": "Sensitive economic profile",
            "verification_status": "verified",
            "evidence_ids": ["ev-party-id"],
        },
    ]
    payload["party_identity_document"] = _verified_identity(
        "ev-party-id", "PARTY-DOC-SECRET"
    )
    payload["representatives"] = [
        {
            "representative_reference": "REP-EXECUTOR-01",
            "role": "executor",
            "authority_basis": "Recorded appointment evidence",
            "evidence_ids": ["ev-rep-1"],
            "identity_document": _verified_identity("ev-rep-1", "REP-DOC-SECRET-01"),
        },
        {
            "representative_reference": "REP-LEGAL-02",
            "role": "legal_representative",
            "authority_basis": "Recorded registry evidence",
            "evidence_ids": ["ev-rep-2"],
            "identity_document": _verified_identity("ev-rep-2", "REP-DOC-SECRET-02"),
        },
    ]
    payload["beneficial_owners"] = [
        {
            "owner_reference": "OWNER-01",
            "control_basis": "Recorded ownership basis one",
            "verification_status": "verified",
            "evidence_ids": ["ev-owner-1"],
            "identity_document": _verified_identity(
                "ev-owner-1", "OWNER-DOC-SECRET-01"
            ),
        },
        {
            "owner_reference": "OWNER-02",
            "control_basis": "Recorded ownership basis two",
            "verification_status": "verified",
            "evidence_ids": ["ev-owner-2"],
            "identity_document": _verified_identity(
                "ev-owner-2", "OWNER-DOC-SECRET-02"
            ),
        },
    ]
    payload["screening_results"] = [
        {
            "screening_id": f"screening-{subject.casefold()}-{screening_type}",
            "subject_reference": subject,
            "screening_type": screening_type,
            "source_reference": f"controlled-{screening_type}-source",
            "checked_at": "2026-01-31T09:30:00+00:00",
            "outcome": "clear",
            "review_status": "confirmed",
            "evidence_ids": [screening_evidence_ids[(subject, screening_type)]],
            "professional_resolution": None,
        }
        for subject in subjects
        for screening_type in ("pep", "sanctions", "country")
    ]
    payload["engagement"]["terms"] = {
        "review_status": "confirmed",
        "duration_months": 24,
        "notice_days": 30,
        "advance_amount": 500,
        "currency": "EUR",
        "payment_terms": "Recorded terms",
        "indexation_basis": "Recorded index basis",
        "insurance_reference": "POLICY-REF-01",
    }
    payload["engagement"]["services"][0]["assessment_status"] = "confirmed"
    for record in payload["applicability"]:
        record["applicability_status"] = (
            "not_applicable" if record["topic"] == "article_28_terms" else "applicable"
        )
        record["review_status"] = "confirmed"
        record["basis"] = "Professional applicability basis recorded."
        record["confirmed_by_role"] = "professional"
        record["confirmed_at"] = PROFESSIONAL_CONFIRMED_AT
    payload["privacy_processing_decisions"] = [
        {
            "decision_id": "privacy-processing-01",
            "purpose": "Perform the confirmed professional engagement.",
            "role": "controller",
            "controller_legal_basis": {
                "code": "contract",
                "basis": "Confirmed contractual processing basis.",
            },
            "processor_authority_reference": None,
            "retention": {
                "status": "defined",
                "period_or_criteria": "Ten years after engagement closure.",
            },
            "source_ids": ["gdpr_regulation", "cndcec_privacy_guide_2025"],
            "review_status": "confirmed",
            "confirmed_by_role": "professional",
            "confirmed_at": PROFESSIONAL_CONFIRMED_AT,
        }
    ]
    source_registry = load_source_registry(
        PLUGIN_ROOT / "references" / "source-registry.json"
    )
    sources_by_id = {
        source["source_id"]: source for source in source_registry["sources"]
    }
    template_topics = (
        "mandate",
        "privacy_notice",
        "ai_transparency_notice",
        "aml_assessment",
    )
    source_ids_by_topic = {
        record["topic"]: record["source_ids"] for record in payload["applicability"]
    }
    template_references: list[dict[str, Any]] = []
    for topic in template_topics:
        template_path = tmp_path / f"template-{topic}.txt"
        template_path.write_text(
            f"studio template reference for {topic}\n", encoding="utf-8"
        )
        source_ids = source_ids_by_topic[topic]
        source_basis = [sources_by_id[source_id] for source_id in sorted(source_ids)]
        template_references.append(
            {
                "document_type": topic,
                "template_id": f"studio-{topic}",
                "version": "2026.1",
                "local_path": template_path.as_posix(),
                "sha256": sha256_file(template_path),
                "source_ids": source_ids,
                "source_basis_sha256": canonical_json_hash(source_basis),
                "approval_status": "approved",
                "approved_by_role": "professional",
                "approved_at": "2026-01-10T10:00:00+01:00",
                "approval_withdrawn_at": None,
                "reuse_status": "studio_owned",
                "reuse_scope": "studio_clients",
                "jurisdiction": "IT",
                "language": "it",
                "valid_from": "2026-01-01",
                "valid_until": "2026-12-31",
                "review_due_on": "2026-12-01",
            }
        )
    payload["template_references"] = template_references
    _set_aml_scores(payload, 2)
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload)
    return validate_intake(payload)


def _write_intake(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "onboarding_intake.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _bind_client_intake_manifest(
    tmp_path: Path,
    payload: dict[str, Any],
    *,
    status: str,
) -> Path:
    manifest_path = tmp_path / f"client-intake-{status}.json"
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "plugin": "client-intake",
        "workflow": "fascicolo-intake",
        "run_id": "client-intake-run-001",
        "status": status,
        "outputs": [
            {
                "path": (
                    "applied_decisions.json"
                    if status == "final_ready"
                    else "studio_memo.md"
                ),
                "status": status,
            }
        ],
    }
    if status == "final_ready":
        manifest["review_status"] = "final_ready"
        manifest["review_application"] = {"application_status": "final_ready"}
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    payload["client_intake_binding"] = {
        "mode": "client_intake_run",
        "run_id": "client-intake-run-001",
        "final_artifacts_path": manifest_path.as_posix(),
        "final_artifacts_sha256": sha256_file(manifest_path),
    }
    return manifest_path


def _call_mcp_validate(output_dir: Path) -> dict[str, Any]:
    node = shutil.which("node")
    bundled_node = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node"
    )
    if node is None and bundled_node.is_file():
        node = bundled_node.as_posix()
    if node is None:
        pytest.skip("Node.js is required to exercise the client-onboarding MCP server.")
    arguments = {
        "run_intake": load_json(output_dir / "run_intake.json"),
        "review_payload": load_json(output_dir / "review_payload.json"),
        "ui_decisions": load_json(output_dir / "ui_decisions.json"),
        "final_artifacts": load_json(output_dir / "final_artifacts.json"),
    }
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "validate_client_onboarding_review",
            "arguments": arguments,
        },
    }
    completed = subprocess.run(
        [node, str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return json.loads(completed.stdout.strip())


def test_build_template_has_exact_aml_and_screening_contract() -> None:
    payload = build_template(
        "CASE-TEMPLATE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )

    assert {factor["factor_id"] for factor in payload["aml"]["factors_a"]} == set(
        AML_A_FACTOR_IDS
    )
    assert {factor["factor_id"] for factor in payload["aml"]["factors_b"]} == set(
        AML_B_FACTOR_IDS
    )
    assert {
        trigger["trigger_id"]
        for trigger in payload["aml"]["mandatory_enhanced_triggers"]
    } == set(AML_TRIGGER_IDS)
    assert payload["aml"]["table_1_assessment"] == {
        "status": "unknown",
        "review_status": "proposed",
        "basis": "Professional Table 1 applicability assessment required.",
        "confirmed_by_role": None,
        "confirmed_at": None,
    }
    assert {record["screening_type"] for record in payload["screening_results"]} == {
        "pep",
        "sanctions",
        "country",
    }


@pytest.mark.parametrize(
    ("score", "expected_code", "expected_interval", "expected_mode"),
    [
        (1, "not_significant", "[1, 1.6)", "simplified"),
        (1.6, "low_significance", "[1.6, 2.6)", "simplified"),
        (2.6, "medium_significance", "[2.6, 3.6)", "ordinary"),
        (3.6, "high_significance", "[3.6, 4]", "enhanced"),
    ],
)
def test_calculate_aml_maps_exact_band_boundaries(
    score: float,
    expected_code: str,
    expected_interval: str,
    expected_mode: str,
) -> None:
    payload = build_template(
        "CASE-BANDS",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    _set_aml_scores(payload, score)
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload)
    validate_intake(payload)

    result = calculate_aml(payload["aml"])

    assert result["specific_risk"] == score
    assert result["effective_risk"] == score
    assert result["calculated_band"]["code"] == expected_code
    assert result["calculated_band"]["interval"] == expected_interval
    assert result["baseline_verification_mode"] == expected_mode
    assert result["minimum_verification_mode_for_review"] == expected_mode


def test_calculate_aml_section_b_exclusion_requires_professional_confirmation() -> None:
    payload = build_template(
        "CASE-EXCLUSION",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["section_b_mode"] = "excluded_confirmed"
    payload["aml"]["section_b_exclusion_confirmation"] = {
        "confirmed": True,
        "reason": "Confirmed professional scope basis.",
        "confirmed_by_role": "professional",
        "confirmed_at": "2026-01-31T10:00:00+01:00",
    }
    for factor, score in zip(payload["aml"]["factors_a"], (1, 2, 3, 4), strict=True):
        factor["score"] = score
    for factor in payload["aml"]["factors_b"]:
        factor["score"] = None
    payload["aml"]["inherent_risk"] = 2
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload)
    validate_intake(payload)

    result = calculate_aml(payload["aml"])

    assert result["specific_risk"] == 2.5
    assert result["effective_risk"] == 2.35
    assert "Section B exclusion confirmed" in result["specific_risk_formula"]


def test_validate_intake_rejects_unconfirmed_section_b_exclusion() -> None:
    payload = build_template(
        "CASE-BAD-EXCLUSION",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["section_b_mode"] = "excluded_confirmed"
    payload["aml"]["section_b_exclusion_confirmation"] = {
        "confirmed": False,
        "reason": "Not actually confirmed.",
        "confirmed_by_role": "professional",
        "confirmed_at": "2026-01-31T10:00:00+01:00",
    }

    with pytest.raises(ValidationError, match="confirmed=true"):
        validate_intake(payload)


def test_validate_intake_requires_professional_table_1_confirmation_metadata() -> None:
    payload = build_template(
        "CASE-TABLE-1-METADATA",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["table_1_assessment"].update(
        {"status": "no", "review_status": "confirmed"}
    )

    with pytest.raises(ValidationError, match="confirmed_by_role=professional"):
        validate_intake(payload)


def test_validate_intake_rejects_unattributed_confirmed_aml_factor() -> None:
    payload = build_template(
        "CASE-FACTOR-PROVENANCE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["factors_a"][0]["assessment_status"] = "confirmed"

    with pytest.raises(ValidationError, match="confirmed_by_role=professional"):
        validate_intake(payload)


def test_validate_intake_rejects_unattributed_confirmed_mandatory_trigger() -> None:
    payload = build_template(
        "CASE-TRIGGER-PROVENANCE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["mandatory_enhanced_triggers"][0].update(
        {"status": "no", "review_status": "confirmed"}
    )

    with pytest.raises(ValidationError, match="confirmed_by_role=professional"):
        validate_intake(payload)


def test_validate_intake_rejects_unattributed_confirmed_applicability() -> None:
    payload = build_template(
        "CASE-APPLICABILITY-PROVENANCE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["applicability"][0].update(
        {"applicability_status": "applicable", "review_status": "confirmed"}
    )

    with pytest.raises(ValidationError, match="confirmed_by_role=professional"):
        validate_intake(payload)


def test_validate_intake_rejects_naive_professional_confirmation_timestamp() -> None:
    payload = build_template(
        "CASE-FACTOR-TIMESTAMP",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["factors_a"][0].update(
        {
            "assessment_status": "confirmed",
            "confirmed_by_role": "professional",
            "confirmed_at": "2026-01-31T10:00:00",
        }
    )

    with pytest.raises(ValidationError, match="must include a timezone offset"):
        validate_intake(payload)


def test_validate_intake_rejects_provenance_on_proposed_factor() -> None:
    payload = build_template(
        "CASE-PROPOSED-FACTOR-PROVENANCE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["factors_a"][0].update(
        {
            "confirmed_by_role": "professional",
            "confirmed_at": PROFESSIONAL_CONFIRMED_AT,
        }
    )

    with pytest.raises(ValidationError, match="confirmation fields must be null"):
        validate_intake(payload)


def test_confirmed_mandatory_trigger_forces_enhanced_and_unknown_blocks() -> None:
    payload = build_template(
        "CASE-TRIGGER",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["mandatory_enhanced_triggers"][0].update(
        {"status": "yes", "review_status": "confirmed"}
    )
    _confirm_table_1(payload)

    result = calculate_aml(payload["aml"])

    assert result["minimum_verification_mode_for_review"] == "enhanced"
    assert result["confirmed_positive_trigger_ids"] == ["pep_private_capacity"]
    assert result["status"] == "blocked_unknown_mandatory_trigger"


def test_unresolved_table_1_blocks_treatment_and_monitoring() -> None:
    payload = build_template(
        "CASE-TABLE-1-UNRESOLVED",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    _set_aml_scores(payload, 1)
    _confirm_negative_triggers(payload)

    aml_result = calculate_aml(payload["aml"])
    monitoring = build_monitoring_plan(
        payload, aml_result, generated_at="2026-02-01T00:00:00+00:00"
    )

    assert aml_result["status"] == "blocked_unresolved_table_1"
    assert aml_result["baseline_verification_mode"] is None
    assert aml_result["minimum_verification_mode_for_review"] is None
    assert monitoring["status"] == "blocked_table_1_assessment"
    assert monitoring["review_interval_months"] is None
    assert monitoring["next_review_date"] is None


def test_non_significant_table_1_case_uses_conduct_rule_without_fixed_cadence() -> None:
    payload = build_template(
        "CASE-TABLE-1-CONDUCT",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    _set_aml_scores(payload, 1)
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload, status="yes")
    validate_intake(payload)

    aml_result = calculate_aml(payload["aml"])
    monitoring = build_monitoring_plan(
        payload, aml_result, generated_at="2026-02-01T00:00:00+00:00"
    )

    assert aml_result["baseline_verification_mode"] == "conduct_rule"
    assert aml_result["minimum_verification_mode_for_review"] == "conduct_rule"
    assert monitoring["status"] == "not_scheduled_conduct_rule"
    assert monitoring["review_interval_months"] is None
    assert monitoring["next_review_date"] is None


def test_no_declassification_preserves_existing_enhanced_mode() -> None:
    payload = build_template(
        "CASE-NO-DOWNGRADE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload)
    payload["aml"]["current_verification_mode"] = "enhanced"

    result = calculate_aml(payload["aml"])

    assert result["calculated_band"]["code"] == "not_significant"
    assert result["minimum_verification_mode_for_review"] == "enhanced"
    assert result["no_declassification_applied"] is True


def test_monitoring_schedule_clamps_dates_and_requires_enhanced_interval() -> None:
    payload = build_template(
        "CASE-MONITORING",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2024-02-29",
    )
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload)
    payload["aml"]["current_verification_mode"] = "enhanced"
    aml_result = calculate_aml(payload["aml"])

    blocked = build_monitoring_plan(
        payload, aml_result, generated_at="2026-01-01T00:00:00+00:00"
    )
    payload["aml"]["enhanced_review_interval_months"] = 12
    scheduled = build_monitoring_plan(
        payload, aml_result, generated_at="2026-01-01T00:00:00+00:00"
    )

    assert blocked["status"] == "blocked_enhanced_interval_selection"
    assert blocked["next_review_date"] is None
    assert scheduled["review_interval_months"] == 12
    assert scheduled["next_review_date"] == "2025-02-28"
    assert add_months_clamped(date(2024, 1, 31), 1).isoformat() == "2024-02-29"


def test_one_off_engagement_has_no_monitoring_schedule() -> None:
    payload = build_template(
        "CASE-ONE-OFF",
        client_type="individual",
        engagement_kind="one_off",
        assessment_date="2026-01-31",
    )
    _confirm_negative_triggers(payload)
    _confirm_table_1(payload)
    aml_result = calculate_aml(payload["aml"])

    result = build_monitoring_plan(
        payload, aml_result, generated_at="2026-01-01T00:00:00+00:00"
    )

    assert result["status"] == "not_scheduled_one_off"
    assert result["review_interval_months"] is None
    assert result["next_review_date"] is None


def test_initialize_case_writes_owner_only_file_outside_repository(
    tmp_path: Path,
) -> None:
    target = initialize_case(
        tmp_path / "private-case",
        client_reference="CASE-PRIVATE",
        assessment_date="2026-01-31",
    )

    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert load_json(target)["client_reference"] == "CASE-PRIVATE"


def test_output_directory_inside_repository_is_rejected() -> None:
    with pytest.raises(ValidationError, match="outside the source repository"):
        ensure_private_output_directory(PLUGIN_ROOT / "forbidden-case-output")


def test_output_directory_guard_works_without_git_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_root = tmp_path / "installed-client-onboarding"
    installed_scripts = installed_root / "scripts"
    installed_manifest = installed_root / ".codex-plugin" / "plugin.json"
    installed_scripts.mkdir(parents=True)
    installed_manifest.parent.mkdir(parents=True)
    installed_manifest.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        onboarding_core,
        "__file__",
        str(installed_scripts / "onboarding_core.py"),
    )

    allowed = onboarding_core.ensure_private_output_directory(
        tmp_path / "private-client-run"
    )

    assert allowed == (tmp_path / "private-client-run").resolve()
    assert stat.S_IMODE(allowed.stat().st_mode) == 0o700
    with pytest.raises(ValidationError, match="installed plugin directories"):
        onboarding_core.ensure_private_output_directory(installed_root / "run")


def test_package_onboarding_e2e_is_private_reviewable_and_hash_bound(
    tmp_path: Path,
) -> None:
    intake = _complete_intake(tmp_path)
    input_path = _write_intake(tmp_path, intake)
    output_dir = tmp_path / "review-package"

    result = package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    assert result["status"] == "pending_review"
    assert set(path.name for path in output_dir.iterdir()) == set(EXPECTED_ARTIFACTS)
    assert validate_contract(output_dir)["artifact_count"] == len(EXPECTED_ARTIFACTS)
    shared = validate_shared_review_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert shared.ok, shared.errors
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output_dir.iterdir()
    )


def test_review_payload_is_minimized_and_covers_professional_review_types(
    tmp_path: Path,
) -> None:
    intake = _complete_intake(tmp_path)
    input_path = _write_intake(tmp_path, intake)
    output_dir = tmp_path / "review-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    review = load_json(output_dir / "review_payload.json")
    serialized = json.dumps(review, ensure_ascii=False)
    item_types = {item["item_type"] for item in review["items"]}
    table_1_item = next(item for item in review["items"] if item["id"] == "aml:table_1")

    assert {
        "party_fact",
        "representative_fact",
        "beneficial_owner_fact",
        "engagement_service",
        "screening_result",
        "document_applicability",
        "aml_risk_factor",
        "aml_mandatory_trigger",
        "aml_assessment",
        "missing_evidence",
        "document_plan",
        "monitoring_plan",
        "official_source",
        "client_intake_binding",
        "privacy_processing",
        "marketing_consent",
    } <= item_types
    assert table_1_item["data"] == {
        "calculation_status": "table_1_confirmed_no_basis_recorded",
        "minimum_verification_mode_for_review": "simplified",
        "uses_proposed_inputs": False,
        "professional_review_required": True,
    }
    for forbidden_value in (
        "RSSMRA80A01H501U",
        "01234567890",
        "PARTY-DOC-SECRET",
        "REP-DOC-SECRET-01",
        "OWNER-DOC-SECRET-01",
        "CASE-ALPHA",
        "REP-EXECUTOR-01",
        "OWNER-01",
        "controlled-pep-source",
        (tmp_path / "case-evidence").as_posix(),
        "Sensitive registered identity",
    ):
        assert forbidden_value not in serialized
    assert "client_reference" not in review
    assert isinstance(review["source_artifacts"], dict)
    assert set(review["source_artifacts"]) == {
        "facts",
        "sources",
        "applicability",
        "aml",
        "documents",
        "monitoring",
    }


def test_generated_review_payload_passes_mcp_validator(tmp_path: Path) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "review-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    response = _call_mcp_validate(output_dir)

    assert "error" not in response
    assert response["result"]["structuredContent"]["ok"] is True
    assert response["result"]["structuredContent"]["item_count"] > 20


def test_validate_contract_detects_artifact_tampering(tmp_path: Path) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "review-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    path = output_dir / "studio_onboarding_memo.md"
    path.write_text(path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ValidationError, match="hash mismatch"):
        validate_contract(output_dir)


def test_generated_statuses_never_assert_final_client_outcomes(tmp_path: Path) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "review-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    forbidden = {"active", "compliant", "signed"}
    observed_statuses: set[str] = set()
    for path in output_dir.glob("*.json"):
        payload = load_json(path)
        pending: list[Any] = [payload]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key == "status" and isinstance(nested, str):
                        observed_statuses.add(nested.casefold())
                    pending.append(nested)
            elif isinstance(value, list):
                pending.extend(value)

    assert observed_statuses.isdisjoint(forbidden)


def test_client_intake_binding_verifies_final_manifest_without_exposing_identity(
    tmp_path: Path,
) -> None:
    payload = _complete_intake(tmp_path)
    bound_manifest = _bind_client_intake_manifest(
        tmp_path, payload, status="final_ready"
    )
    input_path = _write_intake(tmp_path, payload)
    output_dir = tmp_path / "bound-final-package"

    result = package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    facts = load_json(output_dir / "case_facts_validated.json")
    review = load_json(output_dir / "review_payload.json")
    binding_item = next(
        item for item in review["items"] if item["item_type"] == "client_intake_binding"
    )
    serialized_review = json.dumps(review, ensure_ascii=False)
    assert result["status"] == "pending_review"
    assert (
        facts["client_intake_verification"]["verification_status"]
        == "verified_final_ready"
    )
    assert facts["client_intake_verification"]["manifest_sha256"] == sha256_file(
        bound_manifest
    )
    assert binding_item["data"]["reviewed_client_intake"] is True
    assert binding_item["data"]["manifest_sha256"] == sha256_file(bound_manifest)
    assert "client-intake-run-001" not in serialized_review
    assert bound_manifest.as_posix() not in serialized_review


def test_client_intake_binding_nonfinal_is_relationship_blocker(tmp_path: Path) -> None:
    payload = _complete_intake(tmp_path)
    _bind_client_intake_manifest(tmp_path, payload, status="written_pending_review")
    input_path = _write_intake(tmp_path, payload)
    output_dir = tmp_path / "bound-nonfinal-package"

    result = package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    gate = load_json(output_dir / "final_artifacts.json")["export_gate"]
    assert result["status"] == "blocked"
    assert {blocker["code"] for blocker in gate["domain_blockers"]} >= {
        "bound_client_intake_run_not_final_ready"
    }


def test_client_intake_binding_hash_or_identity_mismatch_hard_fails(
    tmp_path: Path,
) -> None:
    payload = _complete_intake(tmp_path)
    manifest_path = _bind_client_intake_manifest(
        tmp_path, payload, status="final_ready"
    )
    payload["client_intake_binding"]["final_artifacts_sha256"] = "0" * 64
    input_path = _write_intake(tmp_path, payload)

    with pytest.raises(ValidationError, match="byte hash mismatch"):
        package_onboarding(
            input_path,
            tmp_path / "hash-mismatch-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )

    payload["client_intake_binding"]["final_artifacts_sha256"] = sha256_file(
        manifest_path
    )
    manifest = load_json(manifest_path)
    manifest["plugin"] = "wrong-plugin"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    payload["client_intake_binding"]["final_artifacts_sha256"] = sha256_file(
        manifest_path
    )
    input_path = _write_intake(tmp_path, payload)
    with pytest.raises(ValidationError, match="plugin must be client-intake"):
        package_onboarding(
            input_path,
            tmp_path / "identity-mismatch-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )


def test_screening_grid_rejects_missing_duplicate_and_unresolved_metadata() -> None:
    payload = build_template(
        "CASE-SCREENING-GRID",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["representatives"] = [
        {
            "representative_reference": "REP-GRID-01",
            "role": "executor",
            "authority_basis": "Recorded authority basis.",
            "evidence_ids": [],
            "identity_document": _identity_document_for_test(),
        }
    ]
    with pytest.raises(ValidationError, match="every client, representative"):
        validate_intake(payload)

    payload = build_template(
        "CASE-SCREENING-DUPLICATE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    duplicate = copy.deepcopy(payload["screening_results"][0])
    duplicate["screening_id"] = "screening-duplicate-01"
    payload["screening_results"].append(duplicate)
    with pytest.raises(ValidationError, match="duplicate a subject/screening-type"):
        validate_intake(payload)

    payload = build_template(
        "CASE-SCREENING-RESOLUTION",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["screening_results"][0]["professional_resolution"] = None
    with pytest.raises(
        ValidationError, match="professional_resolution must be an object"
    ):
        validate_intake(payload)


def _identity_document_for_test() -> dict[str, Any]:
    return {
        "verification_status": "unknown",
        "document_type": None,
        "document_number": None,
        "issuer": None,
        "issued_on": None,
        "expires_on": None,
        "verified_on": None,
        "verification_method": None,
        "evidence_ids": [],
    }


def test_privacy_role_and_confirmation_conditions_are_enforced() -> None:
    payload = build_template(
        "CASE-PRIVACY",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    decision = payload["privacy_processing_decisions"][0]
    decision.update(
        {
            "review_status": "confirmed",
            "confirmed_by_role": "professional",
            "confirmed_at": "2026-01-31T10:00:00+01:00",
        }
    )
    with pytest.raises(ValidationError, match="role and retention are resolved"):
        validate_intake(payload)

    decision.update(
        {
            "role": "processor",
            "retention": {
                "status": "defined",
                "period_or_criteria": "Per controller instructions.",
            },
            "processor_authority_reference": None,
        }
    )
    with pytest.raises(ValidationError, match="processor_authority_reference"):
        validate_intake(payload)


def test_marketing_refusal_is_marketing_only_and_not_relationship_domain_blocker(
    tmp_path: Path,
) -> None:
    payload = _complete_intake(tmp_path)
    payload["marketing_consent"] = {
        "scope": "marketing_only",
        "request_status": "requested",
        "choice": "refused",
        "purposes": ["studio_updates"],
        "channels": ["email"],
        "requested_at": "2026-01-30T10:00:00+01:00",
        "recorded_at": "2026-01-31T10:00:00+01:00",
        "withdrawn_at": None,
        "evidence_ids": ["ev-party-id"],
        "review_status": "confirmed",
        "confirmed_by_role": "professional",
        "confirmed_at": "2026-01-31T10:00:00+01:00",
    }
    input_path = _write_intake(tmp_path, validate_intake(payload))
    output_dir = tmp_path / "marketing-refused-package"

    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    gate = load_json(output_dir / "final_artifacts.json")["export_gate"]
    assert gate["domain_blockers"] == []
    assert gate["marketing_only_blockers"] == [
        {
            "code": "marketing_refused",
            "reference": "marketing:consent",
            "scope": "marketing_use",
        }
    ]
    assert all(
        blocker["scope"] != "marketing_use" for blocker in gate["domain_blockers"]
    )


def test_template_bytes_source_basis_and_readiness_are_verified(tmp_path: Path) -> None:
    payload = _complete_intake(tmp_path)
    payload["template_references"][0]["sha256"] = "0" * 64
    input_path = _write_intake(tmp_path, payload)
    with pytest.raises(ValidationError, match="Template content hash mismatch"):
        package_onboarding(
            input_path,
            tmp_path / "bad-template-hash-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )

    payload = _complete_intake(tmp_path / "second")
    template = payload["template_references"][0]
    template.update(
        {
            "approval_status": "pending",
            "approved_by_role": None,
            "approved_at": None,
            "reuse_status": "unknown",
            "reuse_scope": None,
            "review_due_on": "2026-01-31",
        }
    )
    input_path = _write_intake(tmp_path / "second", validate_intake(payload))
    output_dir = tmp_path / "pending-template-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    document_plan = load_json(output_dir / "document_plan.json")
    mandate = next(
        document
        for document in document_plan["documents"]
        if document["document_type"] == "mandate"
    )
    assert mandate["status"] == "template_reference_not_ready"
    assert {
        "not_professionally_approved",
        "not_approved_for_reuse",
        "reuse_scope_not_recorded",
        "freshness_review_overdue",
    } <= set(mandate["template_reference"]["blockers"])


@pytest.mark.parametrize("tampered_group", ["domain_blockers", "artifact_blockers"])
def test_ready_export_cannot_retain_domain_or_artifact_blockers(
    tmp_path: Path, tampered_group: str
) -> None:
    payload = _complete_intake(tmp_path)
    if tampered_group == "domain_blockers":
        _bind_client_intake_manifest(tmp_path, payload, status="written_pending_review")
    input_path = _write_intake(tmp_path, payload)
    output_dir = tmp_path / f"gate-{tampered_group}"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    manifest_path = output_dir / "final_artifacts.json"
    manifest = load_json(manifest_path)
    gate = manifest["export_gate"]
    gate["review_blockers"] = []
    if tampered_group == "artifact_blockers":
        gate["artifact_blockers"] = [
            {
                "code": "required_output_invalid",
                "reference": "document_plan.json",
                "scope": "relationship_export",
            }
        ]
    gate["status"] = "ready_for_professional_export"
    gate["relationship_ready"] = True
    manifest["status"] = "ready_for_professional_export"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)

    with pytest.raises(ValidationError, match="requires all relationship"):
        validate_contract(output_dir)


def test_verified_evidence_rejects_hash_mismatch_and_symlink(tmp_path: Path) -> None:
    payload = _complete_intake(tmp_path)
    evidence_path = Path(payload["evidence_register"][0]["local_path"])
    evidence_path.write_text("tampered evidence\n", encoding="utf-8")
    input_path = _write_intake(tmp_path, payload)
    with pytest.raises(ValidationError, match="Evidence hash mismatch"):
        package_onboarding(
            input_path,
            tmp_path / "tampered-evidence-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )

    payload = _complete_intake(tmp_path / "symlink-case")
    target = Path(payload["evidence_register"][0]["local_path"])
    link = target.parent / "evidence-link.txt"
    link.symlink_to(target)
    payload["evidence_register"][0]["local_path"] = link.as_posix()
    input_path = _write_intake(tmp_path / "symlink-case", payload)
    with pytest.raises(ValidationError, match="symbolic link"):
        package_onboarding(
            input_path,
            tmp_path / "symlink-evidence-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )


def test_private_write_rejects_symlink_without_changing_its_target(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim.json"
    victim.write_text('{"preserved": true}\n', encoding="utf-8")
    output_link = tmp_path / "output.json"
    output_link.symlink_to(victim)

    with pytest.raises(ValidationError, match="non-regular output file"):
        onboarding_core.write_private_json(output_link, {"replacement": True})

    assert victim.read_text(encoding="utf-8") == '{"preserved": true}\n'
    assert output_link.is_symlink()


def test_private_write_is_atomic_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "output.json"
    original = '{"preserved": true}\n'
    output_path.write_text(original, encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError(f"simulated replace failure for {source} -> {target}")

    monkeypatch.setattr(onboarding_core.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        onboarding_core.write_private_json(output_path, {"replacement": True})

    assert output_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".output.json.*.tmp")) == []


def test_contract_validation_rejects_symlinked_artifact(tmp_path: Path) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "symlinked-artifact-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    victim = tmp_path / "external-review.json"
    review_path = output_dir / "review_payload.json"
    review_path.replace(victim)
    review_path.symlink_to(victim)

    with pytest.raises(ValidationError, match="must be regular files"):
        validate_contract(output_dir)


def test_contract_validation_rejects_manifest_package_hash_drift(
    tmp_path: Path,
) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "package-hash-drift"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    manifest_path = output_dir / "final_artifacts.json"
    manifest = load_json(manifest_path)
    manifest["package_hash"] = "0" * 64
    onboarding_core.write_private_json(manifest_path, manifest)

    with pytest.raises(ValidationError, match="package_hash"):
        validate_contract(output_dir)


def test_packaging_preserves_existing_review_history(tmp_path: Path) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "immutable-run"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    manifest_path = output_dir / "final_artifacts.json"
    original_manifest = manifest_path.read_bytes()

    with pytest.raises(ValidationError, match="new run directory"):
        package_onboarding(
            input_path,
            output_dir,
            generated_at="2026-02-02T10:00:00+00:00",
        )

    assert manifest_path.read_bytes() == original_manifest


def test_review_lists_only_case_used_runtime_sources(tmp_path: Path) -> None:
    input_path = _write_intake(tmp_path, _complete_intake(tmp_path))
    output_dir = tmp_path / "used-sources-package"
    package_onboarding(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    review = load_json(output_dir / "review_payload.json")
    source_ids = {
        item["data"]["source_id"]
        for item in review["items"]
        if item["item_type"] == "official_source"
    }
    assert "cndcec_modulistica_aml_2026" not in source_ids
    assert source_ids == {
        source_id
        for record in load_json(input_path)["applicability"]
        for source_id in record["source_ids"]
    } | {"gdpr_regulation", "cndcec_privacy_guide_2025"}


def test_runtime_source_registry_rejects_third_party_authority(tmp_path: Path) -> None:
    registry = load_json(PLUGIN_ROOT / "references" / "source-registry.json")
    registry["sources"][0]["authority"] = "third_party_draft"
    path = tmp_path / "invalid-runtime-registry.json"
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="authority is unsupported"):
        load_source_registry(path)
