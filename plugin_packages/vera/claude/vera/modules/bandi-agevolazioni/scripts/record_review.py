"""Record one explicit professional decision against exact artifact hashes."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from case_core import (
    canonical_json_sha256,
    case_lock,
    iso_now,
    load_running_context,
    require_run_artifact,
    safe_identifier,
    write_private_json,
)

__all__ = ["current_scope_hash", "record_review", "main"]

LOGGER = logging.getLogger(__name__)
SCOPES = {"source_baseline", "requirements", "assessments", "dossier"}
DECISIONS = {"accepted", "returned"}


def _artifacts(
    output_dir: Path, *, run_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    intake = require_run_artifact(output_dir / "case_intake.json", run_id=run_id)
    sources = require_run_artifact(output_dir / "source_register.json", run_id=run_id)
    workbench = require_run_artifact(
        output_dir / "application_workbench.json", run_id=run_id
    )
    return intake, sources, workbench


def current_scope_hash(output_dir: Path, *, run_id: str, scope: str) -> str:
    """Hash the exact review scope without assigning semantic meaning."""

    intake, sources, workbench = _artifacts(output_dir, run_id=run_id)
    if scope == "source_baseline":
        payloads: tuple[object, ...] = (sources,)
    elif scope == "requirements":
        payloads = (intake, sources, workbench.get("requirements", []))
    elif scope == "assessments":
        payloads = (
            intake,
            sources,
            workbench.get("requirements", []),
            workbench.get("facts", []),
            workbench.get("assessments", []),
            workbench.get("document_checklist", []),
            workbench.get("expenses", []),
            workbench.get("consistency_checks", []),
        )
    elif scope == "dossier":
        payloads = (intake, sources, workbench)
    else:
        raise ValueError(f"unsupported review scope: {scope}")
    return canonical_json_sha256(*payloads)


def record_review(
    *,
    output_dir: Path,
    client_engagement: Path,
    scope: str,
    decision: str,
    reviewer_id: str,
    reviewer_role: str,
    confirmed_by_user: bool,
    notes: str = "",
) -> dict[str, Any]:
    """Append a user-confirmed decision with explicitly bounded identity assurance."""

    if scope not in SCOPES or decision not in DECISIONS:
        raise ValueError("unsupported review scope or decision")
    reviewer_id = safe_identifier(reviewer_id, field="reviewer_id")
    if not reviewer_role.strip():
        raise ValueError("reviewer_role is required")
    if confirmed_by_user is not True:
        raise ValueError("explicit user confirmation is required")
    context = load_running_context(client_engagement, output_dir=output_dir)
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    with case_lock(output_dir):
        event = {
            "event_id": "",
            "scope": scope,
            "scope_sha256": current_scope_hash(output_dir, run_id=run_id, scope=scope),
            "decision": decision,
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role.strip(),
            "confirmation_basis": "explicit_user_confirmation",
            "identity_assurance": "asserted_not_authenticated",
            "reviewed_at": iso_now(),
            "notes": notes.strip(),
        }
        log_path = output_dir / "review_log.json"
        log = require_run_artifact(log_path, run_id=run_id)
        events = log.get("events")
        if not isinstance(events, list):
            raise ValueError("review_log.json has invalid events")
        event["event_id"] = f"review-{len(events) + 1:04d}"
        events.append(event)
        write_private_json(log_path, log)
        run_state_path = output_dir / "run_state.json"
        run_state = require_run_artifact(run_state_path, run_id=run_id)
        run_state.update(
            {
                "updated_at": iso_now(),
                "phase": f"{scope}_review",
                "status": "reviewed" if decision == "accepted" else "needs_review",
            }
        )
        write_private_json(run_state_path, run_state)
    return event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--scope", required=True, choices=sorted(SCOPES))
    parser.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewer-role", required=True)
    parser.add_argument(
        "--confirmed-by-user",
        action="store_true",
        help="Record only after the user explicitly confirms this exact decision.",
    )
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    event = record_review(
        output_dir=args.output_dir,
        client_engagement=args.client_engagement,
        scope=args.scope,
        decision=args.decision,
        reviewer_id=args.reviewer_id,
        reviewer_role=args.reviewer_role,
        confirmed_by_user=args.confirmed_by_user,
        notes=args.notes,
    )
    LOGGER.info("Recorded %s for %s", event["decision"], event["scope"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
