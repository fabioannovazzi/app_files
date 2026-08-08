#!/usr/bin/env python3
"""Record a professional review decision for one current contribution scope."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    atomic_write_json,
    load_json,
    recompute_contribution_digest,
    utc_now,
    validate_schema,
    verify_package_manifest,
    verify_visual_assessment,
    verify_visual_manifest,
    workflow_lock,
)

__all__ = ["record_review", "record_review_bundle", "main"]

LOGGER = logging.getLogger(__name__)
DECISIONS = {"accepted", "returned", "rejected"}


def record_review(
    run_dir: Path,
    *,
    scope: str,
    decision: str,
    reviewer: str,
    note: str,
    confirmed_by_user: bool,
    quality_checklist_confirmed: bool,
) -> Path:
    """Append one digest-bound, locally asserted review event."""

    if not confirmed_by_user:
        raise ValueError("Review recording requires --confirmed-by-user")
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported review decision: {decision}")
    root = run_dir.resolve()
    with workflow_lock(root):
        workbench = load_json(root / "content_workbench.json")
        contribution_digest = recompute_contribution_digest(root)
        artifact_digest = None
        visual_assessment_digest = None
        post_generation_scopes = workbench.get("post_generation_review_scopes", [])
        if scope == "rendered_output":
            if scope not in post_generation_scopes:
                raise ValueError("Rendered output review is not required for this run")
            if decision == "accepted" and not quality_checklist_confirmed:
                raise ValueError(
                    "Accepted rendered output requires --quality-checklist-confirmed"
                )
            artifact_digest = verify_visual_manifest(root)
            if decision == "accepted":
                visual_assessment_digest = verify_visual_assessment(root)
        elif scope == "packaged_output":
            if scope not in post_generation_scopes:
                raise ValueError("Packaged output review is not required for this run")
            artifact_digest = verify_package_manifest(root)
        elif scope not in workbench["required_review_scopes"]:
            raise ValueError(f"Scope is not required for this contribution: {scope}")
        log_path = root / "review_log.json"
        review_log = load_json(log_path)
        event = {
            "event_id": f"REVIEW-{len(review_log['events']) + 1:04d}",
            "scope": scope,
            "decision": decision,
            "reviewer": reviewer,
            "reviewer_role": "commercialista_or_authorized_professional",
            "reviewer_identity_asserted_not_authenticated": True,
            "confirmed_by_user": True,
            "note": note,
            "input_digest": workbench["input_digest"],
            "contribution_digest": contribution_digest,
            "reviewed_at": utc_now(),
        }
        if artifact_digest is not None:
            event["artifact_digest"] = artifact_digest
        if scope == "rendered_output":
            event["quality_checklist_confirmed"] = quality_checklist_confirmed
            if visual_assessment_digest is not None:
                event["visual_assessment_digest"] = visual_assessment_digest
        review_log["events"].append(event)
        atomic_write_json(log_path, review_log)
        return log_path


def record_review_bundle(
    run_dir: Path,
    bundle_path: Path,
    *,
    reviewer: str,
    confirmed_by_user: bool,
) -> Path:
    """Record every semantic scope from one visible, user-confirmed review matrix."""

    if not confirmed_by_user:
        raise ValueError("Review recording requires --confirmed-by-user")
    root = run_dir.resolve()
    with workflow_lock(root):
        bundle = load_json(bundle_path)
        validate_schema(bundle, "review_bundle.schema.json")
        workbench = load_json(root / "content_workbench.json")
        if bundle["run_id"] != workbench["run_id"]:
            raise ValueError("Review bundle run_id mismatch")
        decisions = bundle["decisions"]
        scopes = [row["scope"] for row in decisions]
        if len(scopes) != len(set(scopes)):
            raise ValueError("Review bundle repeats a scope")
        if set(scopes) != set(workbench["required_review_scopes"]):
            raise ValueError(
                "Review bundle must cover every current semantic scope exactly"
            )
        contribution_digest = recompute_contribution_digest(root)
        log_path = root / "review_log.json"
        review_log = load_json(log_path)
        session_id = (
            f"REVIEW-SESSION-{len(review_log['events']) + 1:04d}-"
            f"{contribution_digest[:12]}"
        )
        reviewed_at = utc_now()
        events: list[dict[str, Any]] = []
        for offset, row in enumerate(decisions, start=1):
            events.append(
                {
                    "event_id": f"REVIEW-{len(review_log['events']) + offset:04d}",
                    "review_session_id": session_id,
                    "scope": row["scope"],
                    "decision": row["decision"],
                    "reviewer": reviewer,
                    "reviewer_role": "commercialista_or_authorized_professional",
                    "reviewer_identity_asserted_not_authenticated": True,
                    "confirmed_by_user": True,
                    "note": row["note"],
                    "input_digest": workbench["input_digest"],
                    "contribution_digest": contribution_digest,
                    "reviewed_at": reviewed_at,
                }
            )
        review_log["events"].extend(events)
        atomic_write_json(log_path, review_log)
        return log_path


def main(argv: list[str] | None = None) -> int:
    """Record one review event."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--scope")
    parser.add_argument("--decision", choices=sorted(DECISIONS))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--confirmed-by-user", action="store_true")
    parser.add_argument("--quality-checklist-confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.bundle is not None:
            if args.scope is not None or args.decision is not None:
                raise ValueError("Use either --bundle or --scope/--decision")
            path = record_review_bundle(
                args.run_dir,
                args.bundle,
                reviewer=args.reviewer,
                confirmed_by_user=args.confirmed_by_user,
            )
        else:
            if args.scope is None or args.decision is None:
                raise ValueError("--scope and --decision are required without --bundle")
            path = record_review(
                args.run_dir,
                scope=args.scope,
                decision=args.decision,
                reviewer=args.reviewer,
                note=args.note,
                confirmed_by_user=args.confirmed_by_user,
                quality_checklist_confirmed=args.quality_checklist_confirmed,
            )
    except (OSError, ValueError) as exc:
        LOGGER.error("REVIEW_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded review decision: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
