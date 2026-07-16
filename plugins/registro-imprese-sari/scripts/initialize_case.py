"""Initialize private draft files for a Registro Imprese/SARI case."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from case_core import (
    PLUGIN_NAME,
    ensure_safe_output_dir,
    iso_now,
    safe_identifier,
    validate_iso_date,
    write_private_json,
)

__all__ = ["initialize_case", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def initialize_case(
    output_dir: Path,
    *,
    run_id: str,
    reference_date: str,
    client_reference: str,
    language: str = "it",
) -> dict[str, Path]:
    """Create bounded empty drafts without choosing legal classifications."""

    run_id = safe_identifier(run_id, field="run_id")
    client_reference = safe_identifier(client_reference, field="client_reference")
    reference_date = validate_iso_date(reference_date, field="reference_date")
    language = str(language or "").strip().lower()
    if not 2 <= len(language) <= 12 or not language.replace("-", "").isalpha():
        raise ValueError("language must be a short language tag")
    safe_output = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    intake_path = safe_output / "case_intake_draft.json"
    plan_path = safe_output / "practice_plan_draft.json"
    run_path = safe_output / "run_intake.json"
    if any(path.exists() for path in (intake_path, plan_path, run_path)):
        raise FileExistsError("case draft files already exist; do not overwrite them")
    write_private_json(
        intake_path,
        {
            "schema_version": "1.0",
            "plugin": PLUGIN_NAME,
            "run_id": run_id,
            "reference_date": reference_date,
            "client_reference": client_reference,
            "competent_chamber": {
                "tenant": "",
                "name": "",
                "territorial_basis": "",
                "confirmation_status": "unknown",
            },
            "subject": {
                "legal_form": "",
                "confirmation_status": "unknown",
            },
            "activity": {
                "description": "",
                "classification_status": "unknown",
                "ateco_proposal": None,
            },
            "requested_operation": {
                "description": "",
                "position_types": [],
                "effective_date": None,
                "confirmation_status": "unknown",
            },
            "current_positions": [],
            "professional_question": "",
            "processing_authorization": {
                "approved": False,
                "approval_id": "",
                "approved_by_role": "",
                "recorded_at": "",
            },
        },
    )
    write_private_json(
        plan_path,
        {
            "schema_version": "1.0",
            "plugin": PLUGIN_NAME,
            "run_id": run_id,
            "case_summary": "",
            "classification_proposals": [],
            "position_matrix": [],
            "dire_steps": [],
            "required_documents": [],
            "application_fields": [],
            "risks": [],
            "missing_information": [],
            "sari_question_draft": "",
            "limitations": [
                "Bozza per revisione professionale; non costituisce istruzione di deposito.",
                "Nessun accesso, firma o invio a DIRE, Registro Imprese, INPS, INAIL, SUAP o IVASS.",
            ],
            "professional_review": {
                "status": "pending",
                "reviewer_id": None,
                "reviewer_role": None,
                "reviewed_at": None,
                "notes": None,
            },
        },
    )
    write_private_json(
        run_path,
        {
            "schema_version": "1.0",
            "plugin": PLUGIN_NAME,
            "workflow": PLUGIN_NAME,
            "run_id": run_id,
            "reference_date": reference_date,
            "created_at": iso_now(),
            "language": language,
            "input_paths": [],
            "output_dir": safe_output.as_posix(),
            "inferred_task": (
                "Prepare a source-backed Registro Imprese/DIRE position-opening "
                "draft for professional review."
            ),
            "assumptions": [
                "Initialization does not choose a legal classification, recipient position, or DIRE field."
            ],
            "unresolved_questions": [
                "Confirm the competent chamber, subject, activity, requested operation, and effective date."
            ],
            "dependency_check": {
                "status": "not_recorded",
                "command": ["python", "scripts/check_dependencies.py"],
                "requirements": ["requirements.txt"],
            },
            "status": "pending",
            "data_posture": {
                "local_files_read": [],
                "model_excerpts_sent": [],
                "external_connectors_used": [],
                "upload_paths_used": [],
                "hosted_notebook_execution_used": False,
                "remote_sql_execution_used": False,
                "private_local_output": True,
                "direct_identifiers_excluded_from_case_json": True,
                "network_calls_by_default": False,
                "credentials_or_session_export": False,
                "portal_submission": False,
            },
            "execution_trace": [
                {
                    "step_id": "initialize_case",
                    "kind": "deterministic_initialization",
                    "command": [
                        "python",
                        "scripts/initialize_case.py",
                        "--output-dir",
                        safe_output.as_posix(),
                        "--run-id",
                        run_id,
                        "--reference-date",
                        reference_date,
                        "--client-reference",
                        client_reference,
                        "--language",
                        language,
                    ],
                    "execution_location": "local_python",
                    "status": "passed",
                    "inputs": [],
                    "outputs": [intake_path.name, plan_path.name, run_path.name],
                }
            ],
        },
    )
    return {"intake": intake_path, "plan": plan_path, "run_intake": run_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reference-date", required=True)
    parser.add_argument("--client-reference", required=True)
    parser.add_argument("--language", default="it")
    args = parser.parse_args(argv)
    try:
        paths = initialize_case(**vars(args))
    except (OSError, ValueError) as exc:
        LOGGER.error("INITIALIZATION_BLOCKED: %s", exc)
        return 2
    LOGGER.info("Initialized case drafts in %s", paths["run_intake"].parent)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
