from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from new_client_core import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    SCHEMA_VERSION,
    ValidationError,
    build_applicability_plan,
    build_case_facts,
    build_document_plan,
    build_export_domain_blockers,
    build_missing_evidence,
    build_monitoring_plan,
    build_review_payload,
    calculate_aml,
    canonical_json_hash,
    ensure_private_output_directory,
    load_json,
    load_source_registry,
    sha256_file,
    utc_now,
    validate_contract,
    validate_new_client_input,
    validate_source_references,
    verify_client_file_preparation_binding,
    verify_evidence_register,
    verify_template_references,
    write_private_json,
    write_private_text,
)

__all__ = ["build_parser", "main", "package_new_client"]

PLUGIN_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE_REGISTRY = PLUGIN_ROOT / "references" / "source-registry.json"


def _run_id(generated_at: str, input_hash: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", generated_at)
    return f"new-client-{timestamp}-{input_hash[:12]}"


def _write_memo(
    path: Path,
    *,
    intake: Mapping[str, Any],
    aml_result: Mapping[str, Any],
    missing: Mapping[str, Any],
    documents: Mapping[str, Any],
    monitoring: Mapping[str, Any],
    run_id: str,
) -> Path:
    document_statuses = ", ".join(
        f"{record['document_type']}: {record['status']}"
        for record in documents["documents"]
    )
    lines = [
        "# Studio new-client memo",
        "",
        f"- Run ID: `{run_id}`",
        f"- Client reference: `{intake['client_reference']}`",
        f"- Engagement: `{intake['engagement']['kind']}`",
        f"- Package status: `draft_for_professional_review`",
        "",
        "## AML calculation",
        "",
        f"- RI: `{aml_result['inherent_risk']}`",
        f"- RS: `{aml_result['specific_risk']}`",
        f"- RE: `{aml_result['effective_risk']}`",
        f"- Calculated band: `{aml_result['calculated_band']['label_it']}`",
        f"- Table 1 status: `{aml_result['table_1_assessment']['status']}` "
        f"(`{aml_result['table_1_assessment']['review_status']}`)",
        f"- Baseline treatment: `{aml_result['baseline_verification_mode']}`",
        "- Table 1 applicability is an explicit professional decision with a "
        "recorded basis; an unresolved assessment blocks the treatment outcome.",
        "- Formula: `RE = (RI × 30%) + (RS × 70%)`",
        "- This is arithmetic support. The factor scores, exclusions, trigger "
        "findings, and final treatment require professional review.",
        "",
        "## Evidence and decisions",
        "",
        f"- Open information items: `{missing['count']}`",
        f"- AML workflow status: `{aml_result['status']}`",
        f"- Monitoring status: `{monitoring['status']}`",
        f"- Documents: {document_statuses}",
        "",
        "## Review boundary",
        "",
        "No mandate, privacy notice, AI notice, Article 28 terms, or AML form has "
        "been rendered or declared final. This package records only applicability "
        "and verified template references for a professional document plan.",
    ]
    return write_private_text(path, "\n".join(lines))


def _write_client_missing_information_draft(
    path: Path,
    *,
    client_reference: str,
    missing: Mapping[str, Any],
) -> Path:
    lines = [
        "# Draft — request for missing new-client information",
        "",
        f"Client reference: `{client_reference}`",
        "",
        "This is a studio draft. Review and personalize it before sending.",
        "",
    ]
    if missing["items"]:
        lines.extend(["Please provide or clarify the following:", ""])
        for item in missing["items"]:
            lines.append(
                f"- `{item['item_type']}` / `{item['reference']}`: "
                f"{item['reason'].replace('_', ' ')}."
            )
    else:
        lines.append(
            "No mechanically missing items were detected. A professional must still "
            "review completeness and relevance."
        )
    lines.extend(
        [
            "",
            "Do not send identity documents through an unapproved channel. Use the "
            "studio's designated secure collection method.",
        ]
    )
    return write_private_text(path, "\n".join(lines))


def _write_review_handoff(path: Path, *, run_id: str) -> Path:
    return write_private_text(
        path,
        "\n".join(
            [
                "# New Client Review Handoff",
                "",
                f"- Run ID: `{run_id}`",
                "- Review payload: `review_payload.json`",
                "- Pending decisions: `ui_decisions.json`",
                "- Applied decisions: `applied_decisions.json` (created by the review service)",
                "- Final artifact manifest: `final_artifacts.json`",
                "",
                "## Review sequence",
                "",
                "1. Validate `review_payload.json` with the plugin review tool.",
                "2. Review applicability, AML inputs and triggers, missing evidence, "
                "documents, and the monitoring schedule.",
                "3. Save explicit decisions to `ui_decisions.json`.",
                "4. Apply decisions through the persistent review service.",
                "",
                "Review tools: `validate_new_client_review`, "
                "`render_new_client_review`, "
                "`save_new_client_decisions`, and "
                "`apply_new_client_decisions`.",
                "",
                "The static package is a draft. It does not activate a client, sign a "
                "document, or make a professional compliance determination.",
            ]
        ),
    )


def _artifact_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.name,
        "kind": path.suffix.removeprefix("."),
        "status": "written_pending_review",
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if path.name == "review_handoff.md":
        record["required_text"] = [
            "Review Handoff",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ]
        record["qa_checks"] = ["nonempty_text", "required_text"]
    return record


def package_new_client(
    input_path: Path,
    output_dir: Path,
    *,
    source_registry_path: Path = DEFAULT_SOURCE_REGISTRY,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a complete, private and reviewable new-client package."""

    generated_at_value = generated_at or utc_now()
    resolved_input = input_path.expanduser().resolve()
    intake = validate_new_client_input(load_json(resolved_input))
    source_registry = load_source_registry(source_registry_path.expanduser().resolve())
    validate_source_references(intake, source_registry)
    resolved_output = ensure_private_output_directory(output_dir)
    existing = [
        name for name in EXPECTED_ARTIFACTS if (resolved_output / name).exists()
    ]
    if existing:
        raise ValidationError(
            "Output directory already contains new-client artifacts. Preserve that "
            "review history and package the changed case in a new run directory: "
            + ", ".join(existing)
        )

    input_hash = canonical_json_hash(intake)
    run_id = _run_id(generated_at_value, input_hash)
    evidence_verifications = verify_evidence_register(
        intake, base_dir=resolved_input.parent
    )
    client_file_preparation_verification = verify_client_file_preparation_binding(
        intake, base_dir=resolved_input.parent
    )
    template_verifications = verify_template_references(
        intake,
        source_registry,
        base_dir=resolved_input.parent,
        as_of=date.fromisoformat(generated_at_value[:10]),
    )
    aml_result = calculate_aml(intake["aml"])
    case_facts = build_case_facts(
        intake,
        generated_at=generated_at_value,
        client_file_preparation_verification=client_file_preparation_verification,
        evidence_verifications=evidence_verifications,
    )
    applicability = build_applicability_plan(intake, generated_at=generated_at_value)
    missing = build_missing_evidence(
        intake,
        aml_result,
        generated_at=generated_at_value,
        client_file_preparation_verification=client_file_preparation_verification,
    )
    documents = build_document_plan(
        intake,
        generated_at=generated_at_value,
        template_verifications=template_verifications,
    )
    monitoring = build_monitoring_plan(
        intake, aml_result, generated_at=generated_at_value
    )
    export_domain_blockers = build_export_domain_blockers(
        missing, aml_result, documents, monitoring
    )
    registry_artifact = {
        **source_registry,
        "packaged_at": generated_at_value,
        "registry_hash": canonical_json_hash(source_registry),
    }
    review_payload = build_review_payload(
        intake,
        aml_result,
        missing,
        documents,
        monitoring,
        source_registry,
        run_id=run_id,
        generated_at=generated_at_value,
        case_facts_artifact=case_facts,
        applicability_artifact=applicability,
        source_registry_artifact=registry_artifact,
        client_file_preparation_verification=client_file_preparation_verification,
    )
    aml_draft = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at_value,
        "status": "draft_for_professional_review",
        "professional_review_required": True,
        "client_reference": intake["client_reference"],
        "assessment_date": intake["aml"]["assessment_date"],
        "inherent_risk_status": intake["aml"]["inherent_risk_status"],
        "factors_a": intake["aml"]["factors_a"],
        "factors_b": intake["aml"]["factors_b"],
        "section_b_mode": intake["aml"]["section_b_mode"],
        "section_b_exclusion_confirmation": intake["aml"].get(
            "section_b_exclusion_confirmation"
        ),
        "table_1_assessment": intake["aml"]["table_1_assessment"],
        "mandatory_enhanced_triggers": intake["aml"]["mandatory_enhanced_triggers"],
        "calculation_summary": {
            "effective_risk": aml_result["effective_risk"],
            "calculated_band": aml_result["calculated_band"],
            "baseline_verification_mode": aml_result["baseline_verification_mode"],
            "minimum_verification_mode_for_review": aml_result[
                "minimum_verification_mode_for_review"
            ],
        },
    }
    local_files_read = [
        resolved_input.as_posix(),
        source_registry_path.expanduser().resolve().as_posix(),
    ]
    local_files_read.extend(
        verification["resolved_path"]
        for verification in evidence_verifications
        if verification.get("resolved_path") is not None
    )
    if client_file_preparation_verification.get("bound_manifest_path") is not None:
        local_files_read.append(
            client_file_preparation_verification["bound_manifest_path"]
        )
    local_files_read.extend(
        verification["resolved_path"] for verification in template_verifications
    )
    local_files_read = list(dict.fromkeys(local_files_read))
    run_intake = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "generated_at": generated_at_value,
        "created_at": generated_at_value,
        "status": "ready_for_review",
        "language": intake["language"],
        "client_reference": intake["client_reference"],
        "input_paths": [resolved_input.as_posix()],
        "output_dir": resolved_output.as_posix(),
        "inferred_task": "prepare_reviewable_professional_new_client",
        "assumptions": [
            "Input factor values and applicability records are professional inputs, "
            "not conclusions produced by the deterministic engine."
        ],
        "unresolved_questions": [item["item_id"] for item in missing["items"]],
        "dependency_check": {
            "status": "ready",
            "dependencies": "python_standard_library_only",
        },
        "input": {
            "path": resolved_input.as_posix(),
            "sha256": sha256_file(resolved_input),
            "canonical_payload_sha256": input_hash,
        },
        "source_registry": {
            "path": source_registry_path.expanduser().resolve().as_posix(),
            "sha256": sha256_file(source_registry_path.expanduser().resolve()),
            "canonical_payload_sha256": canonical_json_hash(source_registry),
        },
        "data_posture": {
            "local_files_read": local_files_read,
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "output_directory_mode": "owner_only_0700",
            "artifact_file_mode": "owner_only_0600",
            "review_payload": "pseudonymous_minimized",
            "sensitive_facts": "local_artifacts_only",
            "external_uploads": [],
        },
        "execution_trace": [
            {
                "step_id": "validate_input_contract",
                "kind": "deterministic_schema_and_reference_validation",
                "status": "passed",
                "execution_location": "local_codex_workspace",
                "command": ["package_new_client.py", "--input", "<local-input>"],
                "inputs": [
                    *local_files_read,
                ],
                "outputs": ["case_facts_validated.json", "source_registry.json"],
            },
            {
                "step_id": "calculate_aml_arithmetic",
                "kind": "deterministic_formula",
                "status": aml_result["status"],
                "professional_review_required": True,
                "execution_location": "local_codex_workspace",
                "command": ["package_new_client.py", "calculate_aml"],
                "inputs": ["case_facts_validated.json"],
                "outputs": [
                    "aml_assessment_draft.json",
                    "aml_calculation_audit.json",
                    "monitoring_plan.json",
                ],
            },
            {
                "step_id": "build_review_artifacts",
                "kind": "deterministic_packaging",
                "status": "passed",
                "professional_review_required": True,
                "execution_location": "local_codex_workspace",
                "command": ["package_new_client.py", "build_review_artifacts"],
                "inputs": [
                    "case_facts_validated.json",
                    "source_registry.json",
                    "aml_calculation_audit.json",
                ],
                "outputs": list(EXPECTED_ARTIFACTS),
            },
        ],
    }
    ui_decisions = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "updated_at": generated_at_value,
        "decided_at": None,
        "decision_source": "professional_review_workbench",
        "review_payload_path": "review_payload.json",
        "status": "pending",
        "decisions": [],
        "decision_count": 0,
    }

    written_paths = [
        write_private_json(resolved_output / "run_intake.json", run_intake),
        write_private_json(resolved_output / "case_facts_validated.json", case_facts),
        write_private_json(resolved_output / "source_registry.json", registry_artifact),
        write_private_json(
            resolved_output / "applicability_plan_validated.json", applicability
        ),
        write_private_json(resolved_output / "aml_assessment_draft.json", aml_draft),
        write_private_json(resolved_output / "aml_calculation_audit.json", aml_result),
        write_private_json(resolved_output / "missing_evidence.json", missing),
        write_private_json(resolved_output / "document_plan.json", documents),
        write_private_json(resolved_output / "monitoring_plan.json", monitoring),
        _write_memo(
            resolved_output / "studio_new_client_memo.md",
            intake=intake,
            aml_result=aml_result,
            missing=missing,
            documents=documents,
            monitoring=monitoring,
            run_id=run_id,
        ),
        _write_client_missing_information_draft(
            resolved_output / "client_missing_information_draft.md",
            client_reference=intake["client_reference"],
            missing=missing,
        ),
        write_private_json(resolved_output / "review_payload.json", review_payload),
        write_private_json(resolved_output / "ui_decisions.json", ui_decisions),
        _write_review_handoff(resolved_output / "review_handoff.md", run_id=run_id),
    ]
    output_records = [_artifact_record(path) for path in written_paths]
    artifact_blockers = [
        {
            "code": "required_output_empty",
            "reference": record["path"],
            "scope": "relationship_export",
        }
        for record in output_records
        if record["size_bytes"] <= 0
    ]
    review_blockers: list[dict[str, str]] = []
    for item in review_payload["items"]:
        if item["item_type"] == "marketing_consent":
            scope = "marketing_use"
        elif item["item_type"] == "document_applicability":
            scope = f"document:{item['data']['topic']}"
        else:
            scope = "relationship_export"
        review_blockers.append(
            {
                "code": "professional_review_pending",
                "reference": item["id"],
                "scope": scope,
            }
        )
    marketing = intake["marketing_consent"]
    marketing_only_blockers: list[dict[str, str]] = []
    marketing_code: str | None = None
    if marketing["request_status"] == "not_requested":
        marketing_code = "marketing_not_requested"
    elif marketing["review_status"] != "confirmed":
        marketing_code = "marketing_choice_pending"
    elif marketing["choice"] == "refused":
        marketing_code = "marketing_refused"
    elif marketing["choice"] == "withdrawn":
        marketing_code = "marketing_withdrawn"
    if marketing_code is not None:
        marketing_only_blockers.append(
            {
                "code": marketing_code,
                "reference": "marketing:consent",
                "scope": "marketing_use",
            }
        )
    required_outputs = [record["path"] for record in output_records]
    relationship_review_blockers = [
        blocker for blocker in review_blockers if blocker["scope"] != "marketing_use"
    ]
    manifest_status = (
        "blocked" if export_domain_blockers or artifact_blockers else "pending_review"
    )
    export_gate = {
        "contract_version": SCHEMA_VERSION,
        "export_scope": "owner_only_professional_review_dossier",
        "evaluated_at": generated_at_value,
        "review_revision": review_payload["review_revision"],
        "status": manifest_status,
        "relationship_ready": False,
        "domain_blockers": export_domain_blockers,
        "review_blockers": review_blockers,
        "artifact_blockers": artifact_blockers,
        "marketing_only_blockers": marketing_only_blockers,
        "required_outputs": required_outputs,
        "basis_hashes": dict(review_payload["basis_hashes"]),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "generated_at": generated_at_value,
        "status": manifest_status,
        "professional_review_required": True,
        "signature_performed": False,
        "client_communication_sent": False,
        "relationship_activation_performed": False,
        "export_gate": export_gate,
        "artifacts": output_records,
        "outputs": output_records,
        "package_hash": canonical_json_hash(
            {path.name: sha256_file(path) for path in written_paths}
        ),
        "explicit_non_outcomes": [
            "No client lifecycle activation",
            "No signature or execution of documents",
            "No professional compliance conclusion",
        ],
        "caveats": [
            "All semantic applicability and AML findings require professional review.",
            "The document plan records verified template references; it does not "
            "render, merge, populate, sign, or send document content.",
        ],
        "next_actions": [
            "Resolve missing or unclear information.",
            "Review every review_payload.json item.",
            "Save and apply explicit professional decisions through the review service.",
        ],
        "blockers": [
            *export_domain_blockers,
            *artifact_blockers,
            *relationship_review_blockers,
        ],
    }
    manifest_path = write_private_json(
        resolved_output / "final_artifacts.json", manifest
    )
    validation = validate_contract(resolved_output)
    return {
        "run_id": run_id,
        "status": manifest_status,
        "output_dir": resolved_output,
        "manifest_path": manifest_path,
        "artifact_count": validation["artifact_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Build a private, reviewable Vera new-client package."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=DEFAULT_SOURCE_REGISTRY,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the packaging command."""

    args = build_parser().parse_args(argv)
    try:
        result = package_new_client(
            args.input,
            args.output_dir,
            source_registry_path=args.source_registry,
        )
    except ValidationError as exc:
        sys.stdout.write(json.dumps({"status": "error", "error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(
        json.dumps(
            {
                **result,
                "output_dir": result["output_dir"].as_posix(),
                "manifest_path": result["manifest_path"].as_posix(),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
