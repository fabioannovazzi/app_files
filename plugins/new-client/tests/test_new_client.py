from __future__ import annotations

import copy
import csv
import json
import shutil
import stat
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
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
import new_client_core
import package_new_client as package_new_client_module
from initialize_case import (
    build_template,
    initialize_case,
)
from initialize_case import main as initialize_main
from new_client_core import (
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
    validate_new_client_input,
)
from package_new_client import package_new_client
from promote_client_file_preparation import promote_client_file_preparation

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


def _complete_new_client_input(tmp_path: Path) -> dict[str, Any]:
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
    payload["representative_posture"] = {
        "status": "recorded",
        "executor_reference": "REP-EXECUTOR-01",
        "basis": "Executor and representative authority recorded.",
        "evidence_ids": ["ev-rep-1"],
        "confirmed_by_role": None,
        "confirmed_at": None,
    }
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
    payload["ownership_status"] = {
        "status": "owners_recorded",
        "basis": "Beneficial owners recorded from controlled evidence.",
        "evidence_ids": ["ev-owner-1", "ev-owner-2"],
        "confirmed_by_role": None,
        "confirmed_at": None,
    }
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
    return validate_new_client_input(payload)


def _write_new_client_input(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "new_client_input.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_phase_one_source_contract(
    run_dir: Path,
    *,
    run_id: str,
    jurisdiction: str = "italy",
    language: str = "it",
    source_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    records = source_rows or [
        {
            "relative_path": "source-record.txt",
            "size_bytes": 19,
            "modified_iso": "2026-01-31T09:30:00",
            "sha256": canonical_json_hash("synthetic phase-one source"),
            "entry_type": "regular_file",
        }
    ]
    regular_records = [
        record for record in records if record["entry_type"] == "regular_file"
    ]
    symlink_records = [
        record for record in records if record["entry_type"] == "symlink_not_followed"
    ]
    run_intake = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": run_id,
        "jurisdiction": jurisdiction,
        "language": language,
        "source_snapshot": {
            "algorithm": "sha256",
            "limits": {
                "max_entry_count": 20_000,
                "max_file_count": 5_000,
                "max_file_bytes": 256 * 1024 * 1024,
                "max_total_bytes": 2 * 1024 * 1024 * 1024,
            },
            "observed": {
                "file_count": len(records),
                "regular_file_count": len(regular_records),
                "symlink_count": len(symlink_records),
                "total_regular_bytes": sum(
                    record["size_bytes"] for record in regular_records
                ),
            },
            "files": records,
        },
    }
    (run_dir / "run_intake.json").write_text(
        json.dumps(run_intake, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    inventory_columns = [
        "relative_path",
        "file_name",
        "extension",
        "size_bytes",
        "modified_iso",
        "sha256",
        "category",
        "confidence",
        "years",
        "notes",
    ]
    with (run_dir / "01_document_inventory.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=inventory_columns)
        writer.writeheader()
        for record in records:
            relative_path = Path(record["relative_path"])
            writer.writerow(
                {
                    "relative_path": record["relative_path"],
                    "file_name": relative_path.name,
                    "extension": relative_path.suffix,
                    "size_bytes": record["size_bytes"],
                    "modified_iso": record["modified_iso"],
                    "sha256": record["sha256"],
                    "category": "documenti non classificati",
                    "confidence": "bassa",
                    "years": "",
                    "notes": (
                        "collegamento simbolico non seguito"
                        if record["entry_type"] == "symlink_not_followed"
                        else ""
                    ),
                }
            )
    return ["run_intake.json", "01_document_inventory.csv"]


def _bind_client_file_preparation_manifest(
    tmp_path: Path,
    payload: dict[str, Any],
    *,
    status: str,
    source_rows: list[dict[str, Any]] | None = None,
) -> Path:
    run_dir = tmp_path / f"client-file-preparation-{status}"
    run_dir.mkdir()
    run_id = "client-file-preparation-run-001"
    source_output_names = _write_phase_one_source_contract(
        run_dir,
        run_id=run_id,
        source_rows=source_rows,
    )
    if status == "final_ready":
        item = {"id": "review-item-1", "item_type": "document_inventory"}
        decision = {
            "item_id": item["id"],
            "item_type": item["item_type"],
            "action": "accept",
            "status": "accepted",
        }
        review_payload = {
            "schema_version": "1.0",
            "plugin": "client-file-preparation",
            "workflow": "client-file-preparation",
            "run_id": run_id,
            "review_type": "client_file_preparation_folder_review",
            "items": [item],
            "item_count": 1,
        }
        review_path = run_dir / "review_payload.json"
        review_path.write_text(
            json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        review_bytes_hash = sha256_file(review_path)
        review_canonical_hash = canonical_json_hash(review_payload)
        json_outputs = {
            "ui_decisions.json": {
                "schema_version": "1.0",
                "plugin": "client-file-preparation",
                "workflow": "client-file-preparation",
                "run_id": run_id,
                "reviewer": "reviewer-binding-01",
                "review_payload_sha256": review_bytes_hash,
                "review_payload_canonical_sha256": review_canonical_hash,
                "decisions": [decision],
                "decision_count": 1,
                "item_count": 1,
                "status": "reviewed",
            },
            "applied_decisions.json": {
                "schema_version": "1.0",
                "plugin": "client-file-preparation",
                "workflow": "client-file-preparation",
                "run_id": run_id,
                "reviewer": "reviewer-binding-01",
                "review_payload": {
                    "path": "review_payload.json",
                    "item_count": 1,
                    "sha256": review_bytes_hash,
                    "canonical_sha256": review_canonical_hash,
                },
                "decisions": [decision],
                "effects": [decision | {"applied": True}],
                "decision_count": 1,
                "item_count": 1,
                "blocker_count": 0,
                "application_status": "final_ready",
            },
        }
        for name, value in json_outputs.items():
            (run_dir / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        (run_dir / "review_handoff.md").write_text(
            "# Review Handoff\n", encoding="utf-8"
        )
        output_names = [
            *source_output_names,
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "review_handoff.md",
        ]
    else:
        output_names = [*source_output_names, "studio_memo.md"]
        (run_dir / "studio_memo.md").write_text(
            "unreviewed studio memo\n", encoding="utf-8"
        )
    outputs = [
        {
            "path": name,
            "status": "final_ready" if name == "applied_decisions.json" else status,
            "size_bytes": (run_dir / name).stat().st_size,
            "sha256": sha256_file(run_dir / name),
        }
        for name in output_names
    ]
    package_hash = canonical_json_hash(
        [
            {
                "path": record["path"],
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
            for record in sorted(outputs, key=lambda item: item["path"])
        ]
    )
    manifest_path = run_dir / "final_artifacts.json"
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": run_id,
        "status": status,
        "outputs": outputs,
        "integrity": {
            "algorithm": "sha256",
            "package_hash_basis": ("sorted_outputs_path_size_sha256_canonical_json_v1"),
            "package_hash": package_hash,
        },
    }
    if status == "final_ready":
        manifest["review_status"] = "final_ready"
        manifest["review_payload_sha256"] = review_bytes_hash
        manifest["review_payload_canonical_sha256"] = review_canonical_hash
        manifest["review_application"] = {
            "application_status": "final_ready",
            "decision_count": 1,
            "item_count": 1,
            "blocker_count": 0,
        }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    payload["client_file_preparation_binding"] = {
        "mode": "client_file_preparation_run",
        "run_id": run_id,
        "final_artifacts_path": manifest_path.as_posix(),
        "final_artifacts_sha256": sha256_file(manifest_path),
        "upstream_package_hash": package_hash,
        "promoted_evidence_ids": [],
    }
    return manifest_path


def _write_promotable_phase_one_run(
    tmp_path: Path,
    *,
    action: str,
    extracted_value: str,
    edit_value: str | None = None,
    jurisdiction: str = "italy",
    language: str = "fr",
) -> Path:
    run_dir = tmp_path / f"promotable-{action}"
    run_dir.mkdir()
    run_id = f"client-file-preparation-{action}-001"
    item_id = "fiscal-field-1"
    review_payload = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": run_id,
        "review_type": "client_file_preparation_folder_review",
        "items": [
            {
                "id": item_id,
                "item_type": "extracted_fiscal_field",
                "source_path": "tax-form.pdf",
                "data": {
                    "relative_path": "tax-form.pdf",
                    "document_kind": "CU",
                    "field_code": "codice_fiscale_1",
                    "value": extracted_value,
                    "normalized_value": extracted_value,
                    "confidence": "alta",
                },
            }
        ],
        "item_count": 1,
    }
    effect: dict[str, Any] = {
        "item_id": item_id,
        "item_type": "extracted_fiscal_field",
        "action": action,
        "applied": True,
    }
    if edit_value is not None:
        effect["edit_value"] = edit_value
    decision = {
        "item_id": item_id,
        "item_type": "extracted_fiscal_field",
        "action": action,
        "status": "edited" if action == "edit" else "accepted",
    }
    if edit_value is not None:
        decision["edit_value"] = edit_value
    review_path = run_dir / "review_payload.json"
    review_path.write_text(
        json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    review_bytes_hash = sha256_file(review_path)
    review_canonical_hash = canonical_json_hash(review_payload)
    applied_decisions = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": run_id,
        "reviewer": "reviewer-promotion-01",
        "review_payload": {
            "path": "review_payload.json",
            "item_count": 1,
            "sha256": review_bytes_hash,
            "canonical_sha256": review_canonical_hash,
        },
        "decisions": [decision],
        "application_status": "final_ready",
        "decision_count": 1,
        "item_count": 1,
        "blocker_count": 0,
        "effects": [effect],
    }
    source_output_names = _write_phase_one_source_contract(
        run_dir,
        run_id=run_id,
        jurisdiction=jurisdiction,
        language=language,
        source_rows=[
            {
                "relative_path": "tax-form.pdf",
                "size_bytes": 97,
                "modified_iso": "2026-01-31T09:30:00",
                "sha256": canonical_json_hash("synthetic reviewed tax form"),
                "entry_type": "regular_file",
            }
        ],
    )
    json_outputs = {
        "ui_decisions.json": {
            "schema_version": "1.0",
            "plugin": "client-file-preparation",
            "workflow": "client-file-preparation",
            "run_id": run_id,
            "reviewer": "reviewer-promotion-01",
            "review_payload_sha256": review_bytes_hash,
            "review_payload_canonical_sha256": review_canonical_hash,
            "decisions": [decision],
            "decision_count": 1,
            "item_count": 1,
            "status": "reviewed",
        },
        "applied_decisions.json": applied_decisions,
    }
    for name, value in json_outputs.items():
        (run_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (run_dir / "review_handoff.md").write_text("# Review Handoff\n", encoding="utf-8")
    output_names = [
        *source_output_names,
        "review_payload.json",
        *json_outputs,
        "review_handoff.md",
    ]
    outputs = [
        {
            "path": name,
            "status": "final_ready" if name == "applied_decisions.json" else "written",
            "size_bytes": (run_dir / name).stat().st_size,
            "sha256": sha256_file(run_dir / name),
        }
        for name in output_names
    ]
    package_hash = canonical_json_hash(
        [
            {
                "path": record["path"],
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
            for record in sorted(outputs, key=lambda item: item["path"])
        ]
    )
    manifest = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": run_id,
        "status": "final_ready",
        "review_status": "final_ready",
        "review_payload_sha256": review_bytes_hash,
        "review_payload_canonical_sha256": review_canonical_hash,
        "review_application": {
            "application_status": "final_ready",
            "decision_count": 1,
            "item_count": 1,
            "blocker_count": 0,
        },
        "outputs": outputs,
        "integrity": {
            "algorithm": "sha256",
            "package_hash_basis": ("sorted_outputs_path_size_sha256_canonical_json_v1"),
            "package_hash": package_hash,
        },
    }
    manifest_path = run_dir / "final_artifacts.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _reseal_bound_phase_one_manifest(
    manifest_path: Path, payload: dict[str, Any]
) -> None:
    manifest = load_json(manifest_path)
    for output in manifest["outputs"]:
        output_path = manifest_path.parent / output["path"]
        output["size_bytes"] = output_path.stat().st_size
        output["sha256"] = sha256_file(output_path)
    package_hash = canonical_json_hash(
        [
            {
                "path": record["path"],
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
            for record in sorted(manifest["outputs"], key=lambda item: item["path"])
        ]
    )
    manifest["integrity"]["package_hash"] = package_hash
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    binding = payload["client_file_preparation_binding"]
    binding["final_artifacts_sha256"] = sha256_file(manifest_path)
    binding["upstream_package_hash"] = package_hash


def _phase_one_inventory_rows(
    inventory_path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    with inventory_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _write_phase_one_inventory_rows(
    inventory_path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _new_client_node_binary() -> str:
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
        pytest.skip("Node.js is required to exercise the new-client MCP server.")
    return node


def _call_new_client_mcp(
    output_dir: Path,
    tool_name: str,
    *,
    extra_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    arguments = {
        "run_intake": load_json(output_dir / "run_intake.json"),
        "review_payload": load_json(output_dir / "review_payload.json"),
        "ui_decisions": load_json(output_dir / "ui_decisions.json"),
        "final_artifacts": load_json(output_dir / "final_artifacts.json"),
    }
    arguments.update(extra_arguments or {})
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    completed = subprocess.run(
        [
            _new_client_node_binary(),
            str(PLUGIN_ROOT / "mcp" / "server.cjs"),
            "--stdio",
        ],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return json.loads(completed.stdout.strip())


def _call_mcp_validate(output_dir: Path) -> dict[str, Any]:
    return _call_new_client_mcp(output_dir, "validate_new_client_review")


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
    assert payload["language"] == "it"


def test_new_client_input_rejects_unsupported_language() -> None:
    payload = build_template(
        "CASE-LANGUAGE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["language"] = "pt"

    with pytest.raises(
        ValidationError, match="language must be one of it, en, fr, de, es"
    ):
        validate_new_client_input(payload)


def test_initializer_cli_writes_supported_non_italian_language(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = initialize_main(
        [
            "--case-dir",
            (tmp_path / "german-case").as_posix(),
            "--client-reference",
            "CASE-LANGUAGE",
            "--language",
            "de",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert load_json(Path(report["path"]))["language"] == "de"


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
    validate_new_client_input(payload)

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
    validate_new_client_input(payload)

    result = calculate_aml(payload["aml"])

    assert result["specific_risk"] == 2.5
    assert result["effective_risk"] == 2.35
    assert "Section B exclusion confirmed" in result["specific_risk_formula"]


def test_validate_new_client_input_rejects_unconfirmed_section_b_exclusion() -> None:
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
        validate_new_client_input(payload)


def test_validate_new_client_input_requires_professional_table_1_confirmation_metadata() -> (
    None
):
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
        validate_new_client_input(payload)


def test_validate_new_client_input_rejects_unattributed_confirmed_aml_factor() -> None:
    payload = build_template(
        "CASE-FACTOR-PROVENANCE",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-01-31",
    )
    payload["aml"]["factors_a"][0]["assessment_status"] = "confirmed"

    with pytest.raises(ValidationError, match="confirmed_by_role=professional"):
        validate_new_client_input(payload)


def test_validate_new_client_input_rejects_unattributed_confirmed_mandatory_trigger() -> (
    None
):
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
        validate_new_client_input(payload)


def test_validate_new_client_input_rejects_unattributed_confirmed_applicability() -> (
    None
):
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
        validate_new_client_input(payload)


def test_validate_new_client_input_rejects_naive_professional_confirmation_timestamp() -> (
    None
):
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
        validate_new_client_input(payload)


def test_validate_new_client_input_rejects_provenance_on_proposed_factor() -> None:
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
        validate_new_client_input(payload)


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
    validate_new_client_input(payload)

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


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "it",
            {
                "privacy": "Decisione sul trattamento dei dati — finalità 01",
                "marketing": "Consenso marketing separato",
                "applicability": "Applicabilità — incarico professionale",
                "table_1": "Applicabilità della Tabella 1 antiriciclaggio",
                "monitoring": "Calendario dei riesami periodici",
                "profile": "Profilo del cliente e documenti di identità",
                "structure": "Rappresentanti, esecutore e titolarità effettiva",
                "engagement": "Ambito e condizioni dell’incarico",
                "screening": "Copertura delle verifiche — CASE-ALPHA",
                "aml_section": ("Sezione A dei fattori di rischio antiriciclaggio"),
                "triggers": "Indicatori che impongono misure rafforzate",
            },
        ),
        (
            "en",
            {
                "privacy": "Privacy processing decision — purpose 01",
                "marketing": "Separate marketing-consent record",
                "applicability": "Applicability — professional engagement",
                "table_1": "AML Table 1 applicability",
                "monitoring": "Ongoing-review schedule",
                "profile": "Client profile and identity evidence",
                "structure": "Representatives, executor and beneficial ownership",
                "engagement": "Engagement scope and terms",
                "screening": "Screening coverage — CASE-ALPHA",
                "aml_section": "AML risk-factor section A",
                "triggers": "Mandatory enhanced-measure triggers",
            },
        ),
        (
            "fr",
            {
                "privacy": (
                    "Décision relative au traitement des données — finalité 01"
                ),
                "marketing": "Consentement marketing distinct",
                "applicability": "Applicabilité — mission professionnelle",
                "table_1": "Applicabilité du tableau 1 LCB-FT",
                "monitoring": "Calendrier des réexamens périodiques",
                "profile": "Profil du client et justificatifs d’identité",
                "structure": ("Représentants, exécutant et bénéficiaires effectifs"),
                "engagement": "Périmètre et conditions de la mission",
                "screening": ("Couverture des vérifications — CASE-ALPHA"),
                "aml_section": "Section A des facteurs de risque LCB-FT",
                "triggers": ("Facteurs imposant des mesures de vigilance renforcée"),
            },
        ),
        (
            "de",
            {
                "privacy": "Entscheidung zur Datenverarbeitung — Zweck 01",
                "marketing": "Gesonderte Einwilligung für Marketing",
                "applicability": "Anwendbarkeit — Berufsauftrag",
                "table_1": "Anwendbarkeit der AML-Tabelle 1",
                "monitoring": "Zeitplan für regelmäßige Überprüfungen",
                "profile": "Mandantenprofil und Identitätsnachweise",
                "structure": (
                    "Vertreter, ausführende Person und wirtschaftlich Berechtigte"
                ),
                "engagement": "Umfang und Bedingungen des Auftrags",
                "screening": "Abdeckung der Prüfungen — CASE-ALPHA",
                "aml_section": "Abschnitt A der AML-Risikofaktoren",
                "triggers": "Auslöser für verpflichtende verstärkte Maßnahmen",
            },
        ),
        (
            "es",
            {
                "privacy": "Decisión sobre el tratamiento de datos — finalidad 01",
                "marketing": "Consentimiento de marketing separado",
                "applicability": "Aplicabilidad — encargo profesional",
                "table_1": "Aplicabilidad de la tabla 1 de prevención del blanqueo",
                "monitoring": "Calendario de revisiones periódicas",
                "profile": "Perfil del cliente y documentos de identidad",
                "structure": "Representantes, ejecutor y titularidad real",
                "engagement": "Alcance y condiciones del encargo",
                "screening": "Cobertura de las verificaciones — CASE-ALPHA",
                "aml_section": "Sección A de los factores de riesgo de blanqueo",
                "triggers": "Indicadores que exigen medidas reforzadas",
            },
        ),
    ],
    ids=("italian", "english", "french", "german", "spanish"),
)
def test_package_localizes_professional_review_copy(
    tmp_path: Path,
    language: str,
    expected: dict[str, str],
) -> None:
    intake = _complete_new_client_input(tmp_path)
    intake["language"] = language
    input_path = _write_new_client_input(tmp_path, intake)
    output_dir = tmp_path / f"{language}-review-package"

    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    review = load_json(output_dir / "review_payload.json")
    items = {item["id"]: item for item in review["items"]}
    titles = {item_id: item["title"] for item_id, item in items.items()}
    assert load_json(output_dir / "run_intake.json")["language"] == language
    assert review["summary"]["language"] == language
    assert titles["privacy:processing-01"] == expected["privacy"]
    assert titles["marketing:consent"] == expected["marketing"]
    assert titles["applicability:mandate"] == expected["applicability"]
    assert titles["aml:table_1"] == expected["table_1"]
    assert titles["monitoring:plan"] == expected["monitoring"]
    assert titles["party:profile"] == expected["profile"]
    assert titles["party:structure"] == expected["structure"]
    assert titles["engagement:scope-and-terms"] == expected["engagement"]
    assert titles["screening_subject:CASE-ALPHA"] == expected["screening"]
    assert titles["aml_factor_section:A"] == expected["aml_section"]
    assert titles["aml:mandatory-trigger-set"] == expected["triggers"]
    assert items["applicability:mandate"]["item_type"] == "document_applicability"
    assert items["applicability:mandate"]["data"]["topic"] == "mandate"
    assert items["applicability:mandate"]["allowed_actions"] == [
        "accept",
        "reject",
        "edit",
        "mark_unclear",
        "request_more_documents",
        "skip",
    ]


def test_package_localizes_grouped_missing_evidence_title(tmp_path: Path) -> None:
    intake = _complete_new_client_input(tmp_path)
    intake["language"] = "de"
    intake["evidence_register"][0]["status"] = "missing"
    input_path = _write_new_client_input(tmp_path, intake)
    output_dir = tmp_path / "de-missing-evidence-review-package"

    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    review = load_json(output_dir / "review_payload.json")
    missing_item = next(
        item for item in review["items"] if item["id"] == "missing:grouped"
    )
    assert missing_item["title"] == "Fehlende Nachweise und ungeklärte Angaben"


def test_output_directory_inside_repository_is_rejected() -> None:
    with pytest.raises(ValidationError, match="outside the source repository"):
        ensure_private_output_directory(PLUGIN_ROOT / "forbidden-case-output")


def test_output_directory_guard_works_without_git_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_root = tmp_path / "installed-new-client"
    installed_scripts = installed_root / "scripts"
    installed_manifest = installed_root / ".codex-plugin" / "plugin.json"
    installed_scripts.mkdir(parents=True)
    installed_manifest.parent.mkdir(parents=True)
    installed_manifest.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        new_client_core,
        "__file__",
        str(installed_scripts / "new_client_core.py"),
    )

    allowed = new_client_core.ensure_private_output_directory(
        tmp_path / "private-client-run"
    )

    assert allowed == (tmp_path / "private-client-run").resolve()
    assert stat.S_IMODE(allowed.stat().st_mode) == 0o700
    with pytest.raises(ValidationError, match="installed plugin directories"):
        new_client_core.ensure_private_output_directory(installed_root / "run")


def test_output_directory_rejects_existing_content_without_mutation(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "existing-case-output"
    output_dir.mkdir()
    marker = output_dir / "prior-review.json"
    marker.write_bytes(b'{"preserve":true}\n')

    with pytest.raises(ValidationError, match="must be new or contain only"):
        ensure_private_output_directory(output_dir)

    assert marker.read_bytes() == b'{"preserve":true}\n'


def test_output_directory_rejects_symlink_traversal_without_mutation(
    tmp_path: Path,
) -> None:
    real_parent = tmp_path / "private-real-parent"
    real_parent.mkdir()
    marker = real_parent / "preserve.txt"
    marker.write_text("keep\n", encoding="utf-8")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValidationError, match="symbolic links"):
        ensure_private_output_directory(linked_parent / "new-case")

    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert not (real_parent / "new-case").exists()


def test_package_new_client_e2e_is_private_reviewable_and_hash_bound(
    tmp_path: Path,
) -> None:
    intake = _complete_new_client_input(tmp_path)
    input_path = _write_new_client_input(tmp_path, intake)
    output_dir = tmp_path / "review-package"

    result = package_new_client(
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


def test_review_payload_preserves_professional_data_and_covers_review_types(
    tmp_path: Path,
) -> None:
    intake = _complete_new_client_input(tmp_path)
    input_path = _write_new_client_input(tmp_path, intake)
    output_dir = tmp_path / "review-package"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    review = load_json(output_dir / "review_payload.json")
    serialized = json.dumps(review, ensure_ascii=False)
    item_types = {item["item_type"] for item in review["items"]}
    table_1_item = next(item for item in review["items"] if item["id"] == "aml:table_1")

    assert {
        "party_profile",
        "party_structure",
        "engagement",
        "screening_subject",
        "document_applicability",
        "aml_factor_section",
        "aml_trigger_set",
        "aml_assessment",
        "monitoring_plan",
        "privacy_processing",
        "marketing_consent",
    } <= item_types
    assert review["item_count"] <= 20
    assert table_1_item["data"] == {
        "calculation_status": "table_1_confirmed_no_basis_recorded",
        "minimum_verification_mode_for_review": "simplified",
        "uses_proposed_inputs": False,
        "professional_review_required": True,
    }
    for professionally_useful_value in (
        "RSSMRA80A01H501U",
        "01234567890",
        "PARTY-DOC-SECRET",
        "REP-DOC-SECRET-01",
        "OWNER-DOC-SECRET-01",
        "CASE-ALPHA",
        "REP-EXECUTOR-01",
        "OWNER-01",
        "screening-case-alpha-pep",
        "controlled-pep-source",
        "Sensitive registered identity",
    ):
        assert professionally_useful_value in serialized
    assert (tmp_path / "case-evidence").as_posix() not in serialized
    assert review["privacy"]["classification"] == "private_professional_review"
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
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "review-package"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    response = _call_mcp_validate(output_dir)

    assert "error" not in response
    assert response["result"]["structuredContent"]["ok"] is True
    assert response["result"]["structuredContent"]["item_count"] <= 20


def _expire_evidence(
    payload: dict[str, Any], _registry: dict[str, Any], deadline: str
) -> None:
    payload["evidence_register"][0]["expires_on"] = deadline


def _expire_primary_identity(
    payload: dict[str, Any], _registry: dict[str, Any], deadline: str
) -> None:
    payload["party_identity_document"]["expires_on"] = deadline


def _expire_representative_identity(
    payload: dict[str, Any], _registry: dict[str, Any], deadline: str
) -> None:
    payload["representatives"][0]["identity_document"]["expires_on"] = deadline


def _expire_owner_identity(
    payload: dict[str, Any], _registry: dict[str, Any], deadline: str
) -> None:
    payload["beneficial_owners"][0]["identity_document"]["expires_on"] = deadline


def _expire_template_validity(
    payload: dict[str, Any], _registry: dict[str, Any], deadline: str
) -> None:
    payload["template_references"][0]["valid_until"] = deadline


def _expire_template_review(
    payload: dict[str, Any], _registry: dict[str, Any], deadline: str
) -> None:
    payload["template_references"][0]["review_due_on"] = deadline


def _expire_source_review(
    _payload: dict[str, Any], registry: dict[str, Any], deadline: str
) -> None:
    registry["currentness"]["review_by"] = deadline


@pytest.mark.parametrize(
    ("deadline_kind", "expire"),
    [
        ("evidence_expires_on", _expire_evidence),
        ("primary_identity_expires_on", _expire_primary_identity),
        ("representative_identity_expires_on", _expire_representative_identity),
        ("beneficial_owner_identity_expires_on", _expire_owner_identity),
        ("template_valid_until", _expire_template_validity),
        ("template_review_due_on", _expire_template_review),
        ("authoritative_source_registry_review_by", _expire_source_review),
    ],
)
def test_mcp_apply_fails_when_material_deadline_expires_after_packaging(
    tmp_path: Path,
    deadline_kind: str,
    expire: Any,
) -> None:
    today = datetime.now(timezone.utc).date()
    package_date = today - timedelta(days=1)
    deadline = package_date.isoformat()
    payload = _complete_new_client_input(tmp_path)
    registry = load_json(PLUGIN_ROOT / "references" / "source-registry.json")
    registry["last_reviewed"] = package_date.isoformat()
    registry["currentness"].update(
        {
            "reviewed_on": package_date.isoformat(),
            "review_by": (today + timedelta(days=30)).isoformat(),
        }
    )
    expire(payload, registry, deadline)
    registry_path = tmp_path / "source-registry.json"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / f"expired-apply-{deadline_kind}"
    package_new_client(
        input_path,
        output_dir,
        source_registry_path=registry_path,
        generated_at=f"{deadline}T10:00:00+00:00",
    )
    review = load_json(output_dir / "review_payload.json")
    temporal = review["temporal_validity"]
    deadline_rows = {row["kind"]: row for row in temporal["deadlines"]}
    assert temporal["valid_through"] == deadline
    assert deadline_rows[deadline_kind]["valid_through"] == deadline
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review["items"]
    ]

    response = _call_new_client_mcp(
        output_dir,
        "apply_new_client_decisions",
        extra_arguments={
            "decisions": decisions,
            "decision_source": "temporal-expiry-test",
            "reviewer": "reviewer-temporal-01",
        },
    )

    result = response["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "ok": False,
        "error": (
            f"New Client temporal validity expired on {deadline}; "
            "regenerate the package before Apply"
        ),
    }
    assert not (output_dir / "applied_decisions.json").exists()


def test_mcp_apply_allows_inclusive_material_deadline_on_current_utc_date(
    tmp_path: Path,
) -> None:
    today = datetime.now(timezone.utc).date()
    deadline = today.isoformat()
    payload = _complete_new_client_input(tmp_path)
    payload["evidence_register"][0]["expires_on"] = deadline
    registry = load_json(PLUGIN_ROOT / "references" / "source-registry.json")
    registry["last_reviewed"] = deadline
    registry["currentness"].update(
        {
            "reviewed_on": deadline,
            "review_by": (today + timedelta(days=30)).isoformat(),
        }
    )
    registry_path = tmp_path / "source-registry.json"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / "inclusive-apply"
    package_new_client(
        input_path,
        output_dir,
        source_registry_path=registry_path,
        generated_at=f"{deadline}T10:00:00+00:00",
    )
    review = load_json(output_dir / "review_payload.json")
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review["items"]
    ]

    response = _call_new_client_mcp(
        output_dir,
        "apply_new_client_decisions",
        extra_arguments={
            "decisions": decisions,
            "decision_source": "temporal-inclusive-test",
            "reviewer": "reviewer-temporal-01",
        },
    )

    result = response["result"]["structuredContent"]
    assert result["ok"] is True
    assert result["persisted"] is True
    assert (output_dir / "applied_decisions.json").is_file()


def test_validate_contract_detects_artifact_tampering(tmp_path: Path) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "review-package"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    path = output_dir / "studio_new_client_memo.md"
    path.write_text(path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ValidationError, match="hash mismatch"):
        validate_contract(output_dir)


def test_generated_statuses_never_assert_final_client_outcomes(tmp_path: Path) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "review-package"
    package_new_client(
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


def test_client_file_preparation_binding_verifies_final_manifest_without_exposing_identity(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    bound_manifest = _bind_client_file_preparation_manifest(
        tmp_path, payload, status="final_ready"
    )
    input_path = _write_new_client_input(tmp_path, payload)
    output_dir = tmp_path / "bound-final-package"

    result = package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    facts = load_json(output_dir / "case_facts_validated.json")
    review = load_json(output_dir / "review_payload.json")
    serialized_review = json.dumps(review, ensure_ascii=False)
    assert result["status"] == "pending_review"
    assert (
        facts["client_file_preparation_verification"]["verification_status"]
        == "verified_final_ready"
    )
    assert facts["client_file_preparation_verification"][
        "manifest_sha256"
    ] == sha256_file(bound_manifest)
    assert all(
        item["item_type"] != "client_file_preparation_binding"
        for item in review["items"]
    )
    assert "client-file-preparation-run-001" not in serialized_review
    assert bound_manifest.as_posix() not in serialized_review


def test_client_file_preparation_binding_accepts_explicit_unfollowed_symlink_record(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    _bind_client_file_preparation_manifest(
        tmp_path,
        payload,
        status="final_ready",
        source_rows=[
            {
                "relative_path": "records/source.txt",
                "size_bytes": 21,
                "modified_iso": "2026-01-31T09:30:00",
                "sha256": canonical_json_hash("synthetic regular source"),
                "entry_type": "regular_file",
            },
            {
                "relative_path": "records/external-link.pdf",
                "size_bytes": 24,
                "modified_iso": "2026-01-31T09:31:00",
                "sha256": "",
                "entry_type": "symlink_not_followed",
            },
        ],
    )

    package_new_client(
        _write_new_client_input(tmp_path, payload),
        tmp_path / "explicit-symlink-record-package",
        generated_at="2026-02-01T10:00:00+00:00",
    )

    verification = load_json(
        tmp_path / "explicit-symlink-record-package" / "case_facts_validated.json"
    )["client_file_preparation_verification"]
    assert verification["source_snapshot_observed"] == {
        "file_count": 2,
        "regular_file_count": 1,
        "symlink_count": 1,
        "total_regular_bytes": 21,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_inventory_output", "missing sealed source provenance outputs"),
        ("missing_source_snapshot", "source_snapshot must be an object"),
        ("wrong_algorithm", "algorithm must be sha256"),
        ("weakened_limit", "must be between 1 and"),
        ("observed_count_drift", "observed does not match"),
        ("non_normalized_path", "normalized, non-empty POSIX relative path"),
        ("duplicate_path", "duplicate relative path"),
        ("negative_size", "must be a non-negative integer"),
        ("invalid_regular_hash", "must be a SHA-256 digest"),
        ("symlink_with_hash", "must have an empty sha256"),
        ("wrong_run_identity", "identity does not match"),
        ("old_inventory_header", "unsupported column contract"),
        ("inventory_path_drift", "does not exactly match inventory"),
        ("inventory_size_drift", "does not exactly match inventory"),
        ("inventory_modified_drift", "does not exactly match inventory"),
        ("inventory_hash_drift", "does not exactly match inventory"),
    ],
)
def test_client_file_preparation_binding_rejects_fabricated_source_snapshot(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    manifest_path = _bind_client_file_preparation_manifest(
        tmp_path, payload, status="final_ready"
    )
    run_intake_path = manifest_path.parent / "run_intake.json"
    inventory_path = manifest_path.parent / "01_document_inventory.csv"
    run_intake = load_json(run_intake_path)
    manifest = load_json(manifest_path)
    inventory_fields, inventory_rows = _phase_one_inventory_rows(inventory_path)

    if mutation == "missing_inventory_output":
        manifest["outputs"] = [
            output
            for output in manifest["outputs"]
            if output["path"] != "01_document_inventory.csv"
        ]
    elif mutation == "missing_source_snapshot":
        run_intake.pop("source_snapshot")
    elif mutation == "wrong_algorithm":
        run_intake["source_snapshot"]["algorithm"] = "sha512"
    elif mutation == "weakened_limit":
        run_intake["source_snapshot"]["limits"]["max_file_count"] = 5_001
    elif mutation == "observed_count_drift":
        run_intake["source_snapshot"]["observed"]["regular_file_count"] = 0
    elif mutation == "non_normalized_path":
        run_intake["source_snapshot"]["files"][0][
            "relative_path"
        ] = "./source-record.txt"
        inventory_rows[0]["relative_path"] = "./source-record.txt"
    elif mutation == "duplicate_path":
        run_intake["source_snapshot"]["files"].append(
            copy.deepcopy(run_intake["source_snapshot"]["files"][0])
        )
    elif mutation == "negative_size":
        run_intake["source_snapshot"]["files"][0]["size_bytes"] = -1
    elif mutation == "invalid_regular_hash":
        run_intake["source_snapshot"]["files"][0]["sha256"] = "z" * 64
    elif mutation == "symlink_with_hash":
        run_intake["source_snapshot"]["files"][0]["entry_type"] = "symlink_not_followed"
        run_intake["source_snapshot"]["observed"].update(
            {
                "regular_file_count": 0,
                "symlink_count": 1,
                "total_regular_bytes": 0,
            }
        )
    elif mutation == "wrong_run_identity":
        run_intake["run_id"] = "client-file-preparation-other-run"
    elif mutation == "old_inventory_header":
        inventory_fields.remove("sha256")
        for row in inventory_rows:
            row.pop("sha256")
    elif mutation == "inventory_path_drift":
        inventory_rows[0]["relative_path"] = "different-source.txt"
    elif mutation == "inventory_size_drift":
        inventory_rows[0]["size_bytes"] = "20"
    elif mutation == "inventory_modified_drift":
        inventory_rows[0]["modified_iso"] = "2026-01-31T09:31:00"
    elif mutation == "inventory_hash_drift":
        inventory_rows[0]["sha256"] = "0" * 64
    else:  # pragma: no cover - parameter list is the exhaustive mutation source.
        raise AssertionError(f"Unhandled mutation: {mutation}")

    run_intake_path.write_text(
        json.dumps(run_intake, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_phase_one_inventory_rows(
        inventory_path,
        inventory_fields,
        inventory_rows,
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _reseal_bound_phase_one_manifest(manifest_path, payload)

    with pytest.raises(ValidationError, match=message):
        package_new_client(
            _write_new_client_input(tmp_path, payload),
            tmp_path / f"fabricated-source-snapshot-{mutation}",
            generated_at="2026-02-01T10:00:00+00:00",
        )


def test_client_file_preparation_binding_nonfinal_is_relationship_blocker(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    _bind_client_file_preparation_manifest(
        tmp_path, payload, status="written_pending_review"
    )
    input_path = _write_new_client_input(tmp_path, payload)
    output_dir = tmp_path / "bound-nonfinal-package"

    result = package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    gate = load_json(output_dir / "final_artifacts.json")["export_gate"]
    assert result["status"] == "blocked"
    assert {blocker["code"] for blocker in gate["domain_blockers"]} >= {
        "bound_client_file_preparation_run_not_final_ready"
    }


def test_client_file_preparation_binding_hash_or_identity_mismatch_hard_fails(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    manifest_path = _bind_client_file_preparation_manifest(
        tmp_path, payload, status="final_ready"
    )
    payload["client_file_preparation_binding"]["final_artifacts_sha256"] = "0" * 64
    input_path = _write_new_client_input(tmp_path, payload)

    with pytest.raises(ValidationError, match="byte hash mismatch"):
        package_new_client(
            input_path,
            tmp_path / "hash-mismatch-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )

    payload["client_file_preparation_binding"]["final_artifacts_sha256"] = sha256_file(
        manifest_path
    )
    manifest = load_json(manifest_path)
    manifest["plugin"] = "wrong-plugin"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    payload["client_file_preparation_binding"]["final_artifacts_sha256"] = sha256_file(
        manifest_path
    )
    input_path = _write_new_client_input(tmp_path, payload)
    with pytest.raises(ValidationError, match="plugin must be client-file-preparation"):
        package_new_client(
            input_path,
            tmp_path / "identity-mismatch-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_reviewer", "reviewer"),
        ("missing_effect", "cover every review item"),
        ("unknown_effect_item", "does not reference a real review item"),
        ("wrong_count", "bound_applied_decisions.decision_count"),
        ("incomplete_ui", "cover every review item"),
    ],
)
def test_final_ready_phase_one_binding_rejects_incomplete_review_provenance(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    manifest_path = _bind_client_file_preparation_manifest(
        tmp_path, payload, status="final_ready"
    )
    applied_path = manifest_path.parent / "applied_decisions.json"
    ui_path = manifest_path.parent / "ui_decisions.json"
    applied = load_json(applied_path)
    ui_decisions = load_json(ui_path)
    if mutation == "missing_reviewer":
        applied.pop("reviewer")
    elif mutation == "missing_effect":
        applied["effects"] = []
    elif mutation == "unknown_effect_item":
        applied["effects"][0]["item_id"] = "unknown-review-item"
    elif mutation == "wrong_count":
        applied["decision_count"] = 0
    elif mutation == "incomplete_ui":
        ui_decisions["decisions"] = []
    applied_path.write_text(
        json.dumps(applied, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ui_path.write_text(
        json.dumps(ui_decisions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _reseal_bound_phase_one_manifest(manifest_path, payload)
    input_path = _write_new_client_input(tmp_path, payload)

    with pytest.raises(ValidationError, match=message):
        package_new_client(
            input_path,
            tmp_path / f"bad-review-provenance-{mutation}",
            generated_at="2026-02-01T10:00:00+00:00",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("ui_edit_mismatch", "must match exactly"),
        ("applied_edit_missing", "applied_decisions.edit_value is required"),
        ("effect_edit_mismatch", "must match exactly"),
        ("accepted_with_edit_value", "must not contain edit_value"),
    ],
)
def test_final_ready_phase_one_binding_rejects_edit_value_provenance_drift(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    manifest_path = _bind_client_file_preparation_manifest(
        tmp_path, payload, status="final_ready"
    )
    applied_path = manifest_path.parent / "applied_decisions.json"
    ui_path = manifest_path.parent / "ui_decisions.json"
    applied = load_json(applied_path)
    ui_decisions = load_json(ui_path)
    if mutation == "accepted_with_edit_value":
        ui_decisions["decisions"][0]["edit_value"] = "unexpected replacement"
    else:
        for record in (
            ui_decisions["decisions"][0],
            applied["decisions"][0],
            applied["effects"][0],
        ):
            record["action"] = "edit"
            record["status"] = "edited"
            record["edit_value"] = "reviewed replacement"
        if mutation == "ui_edit_mismatch":
            ui_decisions["decisions"][0]["edit_value"] = "different UI value"
        elif mutation == "applied_edit_missing":
            applied["decisions"][0].pop("edit_value")
        elif mutation == "effect_edit_mismatch":
            applied["effects"][0]["edit_value"] = "different effect value"
    applied_path.write_text(
        json.dumps(applied, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ui_path.write_text(
        json.dumps(ui_decisions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _reseal_bound_phase_one_manifest(manifest_path, payload)
    input_path = _write_new_client_input(tmp_path, payload)

    with pytest.raises(ValidationError, match=message):
        package_new_client(
            input_path,
            tmp_path / f"bad-edit-value-provenance-{mutation}",
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
        validate_new_client_input(payload)

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
        validate_new_client_input(payload)

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
        validate_new_client_input(payload)


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
        validate_new_client_input(payload)

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
        validate_new_client_input(payload)


def test_marketing_refusal_is_marketing_only_and_not_relationship_domain_blocker(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
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
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / "marketing-refused-package"

    package_new_client(
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
    payload = _complete_new_client_input(tmp_path)
    payload["template_references"][0]["sha256"] = "0" * 64
    input_path = _write_new_client_input(tmp_path, payload)
    with pytest.raises(ValidationError, match="Template content hash mismatch"):
        package_new_client(
            input_path,
            tmp_path / "bad-template-hash-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )

    payload = _complete_new_client_input(tmp_path / "second")
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
    input_path = _write_new_client_input(
        tmp_path / "second", validate_new_client_input(payload)
    )
    output_dir = tmp_path / "pending-template-package"
    package_new_client(
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
    payload = _complete_new_client_input(tmp_path)
    if tampered_group == "domain_blockers":
        _bind_client_file_preparation_manifest(
            tmp_path, payload, status="written_pending_review"
        )
    input_path = _write_new_client_input(tmp_path, payload)
    output_dir = tmp_path / f"gate-{tampered_group}"
    package_new_client(
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
    payload = _complete_new_client_input(tmp_path)
    evidence_path = Path(payload["evidence_register"][0]["local_path"])
    evidence_path.write_text("tampered evidence\n", encoding="utf-8")
    input_path = _write_new_client_input(tmp_path, payload)
    with pytest.raises(ValidationError, match="Evidence hash mismatch"):
        package_new_client(
            input_path,
            tmp_path / "tampered-evidence-package",
            generated_at="2026-02-01T10:00:00+00:00",
        )

    payload = _complete_new_client_input(tmp_path / "symlink-case")
    target = Path(payload["evidence_register"][0]["local_path"])
    link = target.parent / "evidence-link.txt"
    link.symlink_to(target)
    payload["evidence_register"][0]["local_path"] = link.as_posix()
    input_path = _write_new_client_input(tmp_path / "symlink-case", payload)
    with pytest.raises(ValidationError, match="symbolic link"):
        package_new_client(
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
        new_client_core.write_private_json(output_link, {"replacement": True})

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

    monkeypatch.setattr(new_client_core.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        new_client_core.write_private_json(output_path, {"replacement": True})

    assert output_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".output.json.*.tmp")) == []


def test_contract_validation_rejects_symlinked_artifact(tmp_path: Path) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "symlinked-artifact-package"
    package_new_client(
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
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "package-hash-drift"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    manifest_path = output_dir / "final_artifacts.json"
    manifest = load_json(manifest_path)
    manifest["package_hash"] = "0" * 64
    new_client_core.write_private_json(manifest_path, manifest)

    with pytest.raises(ValidationError, match="package_hash"):
        validate_contract(output_dir)


def test_packaging_preserves_existing_review_history(tmp_path: Path) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "immutable-run"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    manifest_path = output_dir / "final_artifacts.json"
    original_manifest = manifest_path.read_bytes()

    with pytest.raises(ValidationError, match="new run directory"):
        package_new_client(
            input_path,
            output_dir,
            generated_at="2026-02-02T10:00:00+00:00",
        )

    assert manifest_path.read_bytes() == original_manifest


def test_packaging_failure_does_not_publish_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "transactional-package"

    def fail_after_structured_artifacts(*_args: Any, **_kwargs: Any) -> Path:
        raise OSError("synthetic memo write failure")

    monkeypatch.setattr(
        package_new_client_module,
        "_write_memo",
        fail_after_structured_artifacts,
    )

    with pytest.raises(OSError, match="synthetic memo write failure"):
        package_new_client_module.package_new_client(
            input_path,
            output_dir,
            generated_at="2026-02-01T10:00:00+00:00",
        )

    assert not output_dir.exists()
    assert list(tmp_path.glob(f".{output_dir.name}.*.tmp")) == []


def test_packaging_in_case_directory_retains_the_verified_starter(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "same-directory-case"
    case_dir.mkdir()
    input_path = _write_new_client_input(
        case_dir, _complete_new_client_input(tmp_path / "external-evidence")
    )
    original_input = input_path.read_bytes()

    package_new_client(
        input_path,
        case_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    assert input_path.read_bytes() == original_input
    assert (case_dir / "final_artifacts.json").is_file()
    assert stat.S_IMODE(input_path.stat().st_mode) == 0o600


def test_packaging_failure_in_case_directory_restores_the_starter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = tmp_path / "same-directory-failure"
    case_dir.mkdir()
    input_path = _write_new_client_input(
        case_dir, _complete_new_client_input(tmp_path / "failure-evidence")
    )
    original_input = input_path.read_bytes()

    def fail_after_structured_artifacts(*_args: Any, **_kwargs: Any) -> Path:
        raise OSError("synthetic same-directory failure")

    monkeypatch.setattr(
        package_new_client_module,
        "_write_memo",
        fail_after_structured_artifacts,
    )

    with pytest.raises(OSError, match="synthetic same-directory failure"):
        package_new_client_module.package_new_client(
            input_path,
            case_dir,
            generated_at="2026-02-01T10:00:00+00:00",
        )

    assert list(case_dir.iterdir()) == [input_path]
    assert input_path.read_bytes() == original_input
    assert list(tmp_path.glob(f".{case_dir.name}.*")) == []


def test_review_lists_only_case_used_runtime_sources(tmp_path: Path) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "used-sources-package"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )
    review = load_json(output_dir / "review_payload.json")
    source_ids = {
        source_id for item in review["items"] for source_id in item["source_ids"]
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


def test_run_intake_does_not_claim_model_authority_or_processing_observation(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / "no-false-processing-trace"

    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    run_intake = load_json(output_dir / "run_intake.json")
    assert "processing_authority_declaration" not in run_intake
    assert "observed_processing" not in run_intake
    assert {step["execution_location"] for step in run_intake["execution_trace"]} == {
        "local_python_process"
    }
    assert run_intake["data_posture"]["external_uploads"] == []


def test_non_italian_country_pack_is_rejected_truthfully() -> None:
    with pytest.raises(
        ValidationError, match="No Vera professional-setup country pack"
    ):
        build_template(
            "CASE-COUNTRY-PACK",
            client_type="company",
            engagement_kind="ongoing",
            assessment_date="2026-01-31",
            jurisdiction="CH-GE",
            language="fr",
        )


def test_company_ownership_and_executor_postures_must_be_explicit(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    payload["ownership_status"] = {
        "status": "pending",
        "basis": "Still under review.",
        "evidence_ids": [],
        "confirmed_by_role": None,
        "confirmed_at": None,
    }
    payload["beneficial_owners"] = []
    payload["screening_results"] = [
        screening
        for screening in payload["screening_results"]
        if not screening["subject_reference"].startswith("OWNER-")
    ]
    assert validate_new_client_input(payload)["ownership_status"]["status"] == "pending"

    payload["representative_posture"]["executor_reference"] = "UNKNOWN-EXECUTOR"
    with pytest.raises(
        ValidationError, match="must identify a recorded representative"
    ):
        validate_new_client_input(payload)

    payload = _complete_new_client_input(tmp_path / "posture-confirmation")
    payload["representative_posture"]["confirmed_by_role"] = "professional"
    payload["representative_posture"]["confirmed_at"] = PROFESSIONAL_CONFIRMED_AT
    with pytest.raises(ValidationError, match="must not contain separate confirmation"):
        validate_new_client_input(payload)

    payload = _complete_new_client_input(tmp_path / "executor-role")
    payload["representative_posture"]["executor_reference"] = "REP-LEGAL-02"
    with pytest.raises(ValidationError, match="whose role is executor"):
        validate_new_client_input(payload)


def test_evidence_and_identity_dates_must_be_chronological(tmp_path: Path) -> None:
    payload = _complete_new_client_input(tmp_path)
    payload["evidence_register"][0]["obtained_on"] = "2026-02-01"
    payload["evidence_register"][0]["expires_on"] = "2026-01-31"
    with pytest.raises(
        ValidationError, match="expires_on must not precede obtained_on"
    ):
        validate_new_client_input(payload)

    payload = _complete_new_client_input(tmp_path / "identity-dates")
    payload["party_identity_document"]["issued_on"] = "2035-01-31"
    payload["party_identity_document"]["expires_on"] = "2045-01-31"
    with pytest.raises(ValidationError, match="verified_on must not precede issued_on"):
        validate_new_client_input(payload)


def test_expired_evidence_and_identity_documents_block_export(tmp_path: Path) -> None:
    payload = _complete_new_client_input(tmp_path)
    evidence = next(
        item for item in payload["evidence_register"] if item["evidence_id"] == "ev-cf"
    )
    evidence["expires_on"] = "2026-01-31"
    payload["party_identity_document"]["expires_on"] = "2026-01-31"
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / "expired-package"

    result = package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    reasons = {
        item["reason"]
        for item in load_json(output_dir / "missing_evidence.json")["items"]
    }
    assert result["status"] == "blocked"
    assert {"evidence_expired", "identity_document_expired"} <= reasons


def test_available_evidence_cannot_support_verified_party_and_owner_facts(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    evidence_by_id = {
        item["evidence_id"]: item for item in payload["evidence_register"]
    }
    for evidence_id in ("ev-party-id", "ev-rep-1", "ev-owner-1"):
        evidence_by_id[evidence_id]["status"] = "available"
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / "unverified-support-package"

    result = package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    missing_items = load_json(output_dir / "missing_evidence.json")["items"]
    unverified_ids = {
        item["item_id"]
        for item in missing_items
        if item["reason"] == "supporting_evidence_not_verified"
    }
    assert result["status"] == "blocked"
    assert {
        "party_fact:party-fact-01:evidence",
        "party_identity:primary:evidence",
        "representative_authority:REP-EXECUTOR-01:evidence",
        "representative_identity:REP-EXECUTOR-01:evidence",
        "representative_posture:resolution:evidence",
        "owner:OWNER-01:evidence",
        "owner_identity:OWNER-01:evidence",
        "ownership_status:resolution:evidence",
    } <= unverified_ids


def test_review_groups_all_missing_evidence_into_one_document_request(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    evidence = next(
        item for item in payload["evidence_register"] if item["evidence_id"] == "ev-cf"
    )
    evidence["expires_on"] = "2026-01-31"
    payload["party_identity_document"]["expires_on"] = "2026-01-31"
    input_path = _write_new_client_input(tmp_path, validate_new_client_input(payload))
    output_dir = tmp_path / "grouped-missing-package"

    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    missing_evidence = load_json(output_dir / "missing_evidence.json")
    review = load_json(output_dir / "review_payload.json")
    missing_items = [
        item for item in review["items"] if item["item_type"] == "missing_evidence"
    ]
    assert len(missing_items) == 1
    assert missing_items[0]["id"] == "missing:grouped"
    assert missing_items[0]["recommended_action"] == "request_more_documents"
    assert (
        missing_items[0]["data"]["missing_evidence_count"] == missing_evidence["count"]
    )


def test_confirmed_terms_and_applicability_require_substance_and_case_facts(
    tmp_path: Path,
) -> None:
    payload = _complete_new_client_input(tmp_path)
    payload["engagement"]["terms"] = {
        "review_status": "confirmed",
        "duration_months": None,
        "notice_days": None,
        "advance_amount": None,
        "currency": "EUR",
        "payment_terms": None,
        "indexation_basis": None,
        "insurance_reference": None,
    }
    with pytest.raises(ValidationError, match="at least one substantive term"):
        validate_new_client_input(payload)

    payload = _complete_new_client_input(tmp_path / "case-facts")
    payload["applicability"][0]["case_fact_ids"] = []
    with pytest.raises(ValidationError, match="case_fact_ids must identify"):
        validate_new_client_input(payload)


def test_bound_phase_one_artifact_drift_is_rejected(tmp_path: Path) -> None:
    payload = _complete_new_client_input(tmp_path)
    manifest_path = _bind_client_file_preparation_manifest(
        tmp_path, payload, status="final_ready"
    )
    (manifest_path.parent / "review_payload.json").write_text(
        '{"tampered":true}\n', encoding="utf-8"
    )
    input_path = _write_new_client_input(tmp_path, payload)

    with pytest.raises(ValidationError, match="output (size|hash) mismatch"):
        package_new_client(
            input_path,
            tmp_path / "tampered-upstream",
            generated_at="2026-02-01T10:00:00+00:00",
        )


@pytest.mark.parametrize(
    ("action", "extracted_value", "edit_value", "expected_value"),
    [
        ("accept", "RSSMRA80A01H501U", None, "RSSMRA80A01H501U"),
        ("edit", "RSSMRA80A01H501X", "RSSMRA80A01H501U", "RSSMRA80A01H501U"),
    ],
)
def test_promotion_uses_only_reviewed_unambiguous_tax_code(
    tmp_path: Path,
    action: str,
    extracted_value: str,
    edit_value: str | None,
    expected_value: str,
) -> None:
    manifest_path = _write_promotable_phase_one_run(
        tmp_path,
        action=action,
        extracted_value=extracted_value,
        edit_value=edit_value,
    )

    target = promote_client_file_preparation(
        manifest_path,
        tmp_path / f"promoted-case-{action}",
        client_reference=f"CASE-PROMOTED-{action.upper()}",
        assessment_date="2026-02-01",
        language="fr",
    )

    intake = load_json(target)
    assert intake["jurisdiction"] == "IT"
    assert intake["language"] == "fr"
    assert intake["tax_facts"]["codice_fiscale"] == {
        "value": expected_value,
        "verification_status": "reported",
        "evidence_ids": ["phase1-reviewed-decisions"],
    }
    assert intake["tax_facts"]["partita_iva"]["verification_status"] == "unknown"
    assert intake["party_facts"][0]["fact_id"] == "party-fact-01"
    assert all(
        record["case_fact_ids"] == ["party-fact-01"]
        for record in intake["applicability"]
    )
    assert intake["client_file_preparation_binding"]["promoted_evidence_ids"] == [
        "phase1-reviewed-decisions"
    ]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize("upstream_jurisdiction", ["geneva", "zurich", "uk", "mixed"])
def test_promotion_rejects_unavailable_or_mixed_country_pack(
    tmp_path: Path, upstream_jurisdiction: str
) -> None:
    manifest_path = _write_promotable_phase_one_run(
        tmp_path,
        action="accept",
        extracted_value="RSSMRA80A01H501U",
        jurisdiction=upstream_jurisdiction,
    )

    expected = "mixed-jurisdiction" if upstream_jurisdiction == "mixed" else "No Vera"
    with pytest.raises(ValidationError, match=expected):
        promote_client_file_preparation(
            manifest_path,
            tmp_path / "blocked-country-pack",
            client_reference="CASE-COUNTRY-BLOCKED",
        )


def test_promotion_inherits_and_protects_sealed_language(tmp_path: Path) -> None:
    manifest_path = _write_promotable_phase_one_run(
        tmp_path,
        action="accept",
        extracted_value="RSSMRA80A01H501U",
        language="de",
    )
    inherited = promote_client_file_preparation(
        manifest_path,
        tmp_path / "inherited-language",
        client_reference="CASE-LANGUAGE-INHERITED",
    )
    assert load_json(inherited)["language"] == "de"

    with pytest.raises(ValidationError, match="must match the sealed"):
        promote_client_file_preparation(
            manifest_path,
            tmp_path / "mismatched-language",
            client_reference="CASE-LANGUAGE-MISMATCH",
            language="fr",
        )


@pytest.mark.parametrize(
    ("language", "expected_heading"),
    [
        ("it", "Memo studio — nuovo cliente"),
        ("en", "Studio new-client memo"),
        ("fr", "Note du cabinet — nouveau client"),
        ("de", "Kanzleivermerk — neuer Mandant"),
        ("es", "Memoria del despacho — nuevo cliente"),
    ],
)
def test_generated_studio_outputs_follow_selected_language(
    tmp_path: Path, language: str, expected_heading: str
) -> None:
    case_root = tmp_path / language
    payload = _complete_new_client_input(case_root)
    payload["language"] = language
    for template in payload["template_references"]:
        template["language"] = language
    input_path = _write_new_client_input(case_root, validate_new_client_input(payload))
    output_dir = case_root / "localized-package"

    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    memo = (output_dir / "studio_new_client_memo.md").read_text(encoding="utf-8")
    assert expected_heading in memo


@pytest.mark.parametrize(
    ("language", "memo_label", "missing_reason", "handoff_heading"),
    [
        (
            "it",
            "Fascia calcolata: poco significativo",
            "non risulta disponibile",
            "# Passaggio alla revisione — nuovo cliente",
        ),
        (
            "en",
            "Calculated band: low significance",
            "is not currently available",
            "# New Client Review Handoff",
        ),
        (
            "fr",
            "Niveau calculé: peu significatif",
            "n’est pas disponible",
            "# Transmission pour revue — nouveau client",
        ),
        (
            "de",
            "Berechnete Risikostufe: gering signifikant",
            "liegt derzeit nicht vor",
            "# Übergabe zur Prüfung — neuer Mandant",
        ),
        (
            "es",
            "Nivel calculado: poco significativo",
            "no está disponible actualmente",
            "# Entrega para revisión — nuevo cliente",
        ),
    ],
    ids=("italian", "english", "french", "german", "spanish"),
)
def test_human_facing_package_artifacts_are_fully_localized(
    tmp_path: Path,
    language: str,
    memo_label: str,
    missing_reason: str,
    handoff_heading: str,
) -> None:
    case_root = tmp_path / language
    payload = _complete_new_client_input(case_root)
    payload["language"] = language
    payload["evidence_register"][0]["status"] = "missing"
    for template in payload["template_references"]:
        template["language"] = language
    input_path = _write_new_client_input(case_root, validate_new_client_input(payload))
    output_dir = case_root / "localized-human-artifacts"

    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    memo = (output_dir / "studio_new_client_memo.md").read_text(encoding="utf-8")
    client_draft = (output_dir / "client_missing_information_draft.md").read_text(
        encoding="utf-8"
    )
    handoff = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    missing_json = load_json(output_dir / "missing_evidence.json")
    manifest = load_json(output_dir / "final_artifacts.json")
    handoff_record = next(
        record
        for record in manifest["outputs"]
        if record["path"] == "review_handoff.md"
    )

    assert memo_label in memo
    assert missing_reason in client_draft
    assert handoff.startswith(handoff_heading + "\n")
    assert handoff_heading.removeprefix("# ") in handoff_record["required_text"]
    assert any(
        item["reason"] == "evidence_status_missing" for item in missing_json["items"]
    )
    human_copy = "\n".join((memo, client_draft, handoff))
    for machine_code in (
        "draft_for_professional_review",
        "calculated_for_professional_review",
        "draft_schedule_for_professional_review",
        "approved_reusable_reference_available",
        "evidence_status_missing",
        "evidence_record",
    ):
        assert machine_code not in human_copy
    assert "ev-cf" not in client_draft


def test_complete_case_recommends_accept_without_unprotecting_semantic_items(
    tmp_path: Path,
) -> None:
    input_path = _write_new_client_input(tmp_path, _complete_new_client_input(tmp_path))
    output_dir = tmp_path / "recommendations"
    package_new_client(
        input_path,
        output_dir,
        generated_at="2026-02-01T10:00:00+00:00",
    )

    review = load_json(output_dir / "review_payload.json")
    assert {item["recommended_action"] for item in review["items"]} == {"accept"}
    adapter = load_json(PLUGIN_ROOT / "assets" / "review-workbench-adapter.json")
    protected = set(adapter["bulkProtectedItemTypes"])
    assert {
        "privacy_processing",
        "document_applicability",
        "aml_factor_section",
        "aml_trigger_set",
        "aml_assessment",
    } <= protected
