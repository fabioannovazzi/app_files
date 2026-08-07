"""Initialize a bounded Bandi e agevolazioni Studio Archive run."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from case_core import (
    PLUGIN_NAME,
    case_lock,
    iso_now,
    load_json_object,
    load_running_context,
    relative_run_path,
    safe_identifier,
    validate_iso_date,
    write_private_json,
)

__all__ = ["initialize_case", "main"]

LOGGER = logging.getLogger(__name__)


def initialize_case(
    output_dir: Path,
    *,
    client_engagement: Path,
    reference_date: str,
    client_reference: str,
    language: str = "it",
) -> dict[str, Path]:
    """Create empty drafts without choosing any legal or semantic conclusion."""

    client_reference = safe_identifier(client_reference, field="client_reference")
    reference_date = validate_iso_date(reference_date, field="reference_date")
    language = str(language or "").strip().lower()
    if not 2 <= len(language) <= 12 or not language.replace("-", "").isalpha():
        raise ValueError("language must be a short language tag")
    context = load_running_context(client_engagement, output_dir=output_dir)
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    files = {
        "case_intake": output_dir / "case_intake.json",
        "sources": output_dir / "source_register.json",
        "workbench": output_dir / "application_workbench.json",
        "intelligence": output_dir / "intelligence_register.json",
        "reviews": output_dir / "review_log.json",
        "run_state": output_dir / "run_state.json",
    }
    with case_lock(output_dir):
        if files["run_state"].exists():
            missing = [path.name for path in files.values() if not path.exists()]
            if missing:
                raise ValueError(
                    "initialized case is incomplete; missing: " + ", ".join(missing)
                )
            state = load_json_object(files["run_state"])
            intake = load_json_object(files["case_intake"])
            if state.get("plugin") != PLUGIN_NAME or state.get("run_id") != run_id:
                raise ValueError("existing run_state belongs to another plugin run")
            if (
                intake.get("reference_date") != reference_date
                or intake.get("client_reference") != client_reference
                or state.get("language") != language
            ):
                raise ValueError("existing initialization parameters do not match")
            return files
        # run_state is committed last. Existing draft files therefore represent
        # an interrupted initialization and are safely replaced, making retry
        # idempotent without overwriting a completed run.
        for label, path in files.items():
            if label == "run_state" or not path.exists():
                continue
            payload = load_json_object(path)
            collections = {
                "sources": ("sources", "source_set_revision"),
                "workbench": (
                    "requirements",
                    "facts",
                    "assessments",
                    "document_checklist",
                    "expenses",
                    "form_fields",
                    "narratives",
                    "consistency_checks",
                    "issues",
                ),
                "reviews": ("events",),
                "intelligence": ("runs",),
            }
            if payload.get("plugin") != PLUGIN_NAME or payload.get("run_id") != run_id:
                raise ValueError(f"partial {label} belongs to another plugin run")
            if label == "case_intake":
                material_values = (
                    payload.get("professional_question"),
                    *(
                        payload.get(section, {}).get(field)
                        for section, field in (
                            ("application", "title"),
                            ("application", "issuing_authority"),
                            ("application", "procedure_id"),
                            ("applicant", "legal_name"),
                            ("applicant", "tax_code"),
                            ("applicant", "vat_number"),
                            ("project", "title"),
                            ("project", "summary"),
                            ("project", "requested_amount"),
                        )
                        if isinstance(payload.get(section), dict)
                    ),
                )
                if any(value not in (None, "") for value in material_values):
                    raise ValueError(
                        "run_state is missing but intake contains case work; "
                        "manual recovery is required"
                    )
            if label in collections and any(
                payload.get(key) not in ([], 0) for key in collections[label]
            ):
                raise ValueError(
                    "run_state is missing but existing artifacts contain case work; "
                    "manual recovery is required"
                )
            if label == "workbench" and payload.get("case_summary") not in (None, ""):
                raise ValueError(
                    "run_state is missing but workbench contains case work; "
                    "manual recovery is required"
                )
        created_at = iso_now()
        write_private_json(
            files["case_intake"],
            {
                "schema_version": "1.0",
                "plugin": PLUGIN_NAME,
                "run_id": run_id,
                "reference_date": reference_date,
                "client_reference": client_reference,
                "application": {
                    "title": "",
                    "issuing_authority": "",
                    "procedure_id": "",
                    "submission_deadline": None,
                    "status": "unknown",
                },
                "applicant": {
                    "legal_name": "",
                    "tax_code": "",
                    "vat_number": "",
                    "confirmation_status": "unknown",
                },
                "project": {
                    "title": "",
                    "summary": "",
                    "requested_amount": None,
                    "currency": None,
                    "confirmation_status": "unknown",
                },
                "professional_question": "",
            },
        )
        write_private_json(
            files["sources"],
            {
                "schema_version": "1.0",
                "plugin": PLUGIN_NAME,
                "run_id": run_id,
                "source_set_revision": 0,
                "sources": [],
            },
        )
        write_private_json(
            files["workbench"],
            {
                "schema_version": "1.2",
                "plugin": PLUGIN_NAME,
                "run_id": run_id,
                "case_summary": "",
                "requirements": [],
                "facts": [],
                "assessments": [],
                "document_checklist": [],
                "expenses": [],
                "form_fields": [],
                "narratives": [],
                "consistency_checks": [],
                "issues": [],
                "authority_simulation": {
                    "status": "not_run",
                    "reviewer_perspective": "",
                    "overall_outcome": "not_run",
                    "checks": [],
                },
                "dossier": {
                    "disposition": "review_required",
                    "ready_to_file": False,
                    "limitations": [
                        "Bozza per revisione professionale; Vera non firma e non invia la domanda."
                    ],
                },
            },
        )
        write_private_json(
            files["intelligence"],
            {
                "schema_version": "1.0",
                "contract_version": "bandi-intelligence-v1",
                "plugin": PLUGIN_NAME,
                "run_id": run_id,
                "runs": [],
            },
        )
        write_private_json(
            files["reviews"],
            {
                "schema_version": "1.1",
                "plugin": PLUGIN_NAME,
                "run_id": run_id,
                "events": [],
            },
        )
        write_private_json(
            files["run_state"],
            {
                "schema_version": "1.0",
                "plugin": PLUGIN_NAME,
                "workflow": PLUGIN_NAME,
                "run_id": run_id,
                "created_at": created_at,
                "updated_at": created_at,
                "language": language,
                "phase": "intake",
                "status": "needs_review",
                "source_set_revision": 0,
                "output_dir": relative_run_path(output_dir, context),
                "ready_to_file": False,
                "portal_actions_performed": False,
                "signature_actions_performed": False,
                "submission_actions_performed": False,
            },
        )
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--reference-date", required=True)
    parser.add_argument("--client-reference", required=True)
    parser.add_argument("--language", default="it")
    args = parser.parse_args(argv)
    paths = initialize_case(
        args.output_dir,
        client_engagement=args.client_engagement,
        reference_date=args.reference_date,
        client_reference=args.client_reference,
        language=args.language,
    )
    for label, path in paths.items():
        LOGGER.info("%s: %s", label, path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
