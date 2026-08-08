#!/usr/bin/env python3
"""Record a professional review decision for one current contribution scope."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import (
    atomic_write_json,
    load_json,
    recompute_contribution_digest,
    utc_now,
    verify_package_manifest,
    verify_visual_manifest,
    workflow_lock,
)

__all__ = ["record_review", "main"]

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
        post_generation_scopes = workbench.get("post_generation_review_scopes", [])
        if scope == "rendered_output":
            if scope not in post_generation_scopes:
                raise ValueError("Rendered output review is not required for this run")
            artifact_digest = verify_visual_manifest(root)
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
        review_log["events"].append(event)
        atomic_write_json(log_path, review_log)
        return log_path


def main(argv: list[str] | None = None) -> int:
    """Record one review event."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--decision", choices=sorted(DECISIONS), required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = record_review(
            args.run_dir,
            scope=args.scope,
            decision=args.decision,
            reviewer=args.reviewer,
            note=args.note,
            confirmed_by_user=args.confirmed_by_user,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("REVIEW_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded review decision: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
