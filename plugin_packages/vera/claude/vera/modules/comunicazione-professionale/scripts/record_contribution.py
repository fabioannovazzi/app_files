#!/usr/bin/env python3
"""Record one exact model contribution and prepare its review queue."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    atomic_write_json,
    atomic_write_text,
    canonical_digest,
    load_json,
    required_review_scopes,
    utc_now,
    validate_contribution_semantics,
    validate_input_integrity,
    workflow_lock,
)

__all__ = ["record_contribution", "main"]

LOGGER = logging.getLogger(__name__)


def _review_items(contribution: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "id": "recommendation",
            "item_type": "recommendation",
            "title": f"Recommendation: {contribution['recommendation']}",
            "allowed_actions": ["accept", "reject", "mark_unclear"],
            "recommended_action": (
                "accept"
                if contribution["recommendation"] == "no_publish"
                else "mark_unclear"
            ),
            "data": {"reason": contribution["recommendation_reason"]},
            "evidence": [],
        }
    ]
    for assessment in contribution["source_assessments"]:
        items.append(
            {
                "id": f"source-{assessment['source_id']}",
                "item_type": "source_assessment",
                "title": f"Source {assessment['source_id']}",
                "allowed_actions": [
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                ],
                "recommended_action": "mark_unclear",
                "data": assessment,
                "evidence": [{"source_id": assessment["source_id"]}],
            }
        )
    for claim in contribution["claims"]:
        items.append(
            {
                "id": claim["id"],
                "item_type": "claim",
                "title": claim["statement"],
                "allowed_actions": [
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                ],
                "recommended_action": "mark_unclear",
                "data": claim,
                "evidence": [{"source_ids": claim["source_ids"]}],
            }
        )
    items.append(
        {
            "id": "editorial-value",
            "item_type": "editorial_value",
            "title": "Editorial value and no-slop judgment",
            "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
            "recommended_action": "mark_unclear",
            "data": contribution["editorial_value"],
            "evidence": [],
        }
    )
    if contribution["studio_profile_proposal"] is not None:
        items.append(
            {
                "id": "studio-profile",
                "item_type": "studio_profile",
                "title": "Studio voice and format profile",
                "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
                "recommended_action": "mark_unclear",
                "data": contribution["studio_profile_proposal"],
                "evidence": [],
            }
        )
    for draft in contribution["channel_drafts"]:
        items.append(
            {
                "id": f"draft-{draft['channel']}",
                "item_type": "channel_draft",
                "title": f"{draft['channel']}: {draft['title']}",
                "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
                "recommended_action": "edit",
                "data": draft,
                "evidence": [{"claim_ids": draft["claim_ids"]}],
            }
        )
    if contribution["visual_story"]["slides"]:
        items.append(
            {
                "id": "visual-story",
                "item_type": "visual_story",
                "title": contribution["visual_story"]["title"],
                "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
                "recommended_action": "edit",
                "data": contribution["visual_story"],
                "evidence": [],
            }
        )
    return items


def _handoff_markdown(
    *,
    run_id: str,
    version: int,
    digest: str,
    contribution: dict[str, Any],
    required_scopes: list[str],
    post_generation_scopes: list[str],
) -> str:
    lines = [
        "# Communication review handoff",
        "",
        f"- Run: `{run_id}`",
        f"- Contribution version: `{version}`",
        f"- Contribution digest: `{digest}`",
        f"- Recommendation: **{contribution['recommendation']}**",
        f"- Required review scopes: {', '.join(f'`{scope}`' for scope in required_scopes)}",
        f"- Required post-generation scopes: {', '.join(f'`{scope}`' for scope in post_generation_scopes)}",
        "",
        "## Recommendation basis",
        "",
        contribution["recommendation_reason"],
        "",
        "## Review files",
        "",
        "- `source_register.json`: exact input snapshots and hashes",
        "- `content_workbench.json`: model contribution and provenance",
        "- `review_payload.json`: item-level review queue",
        "- `review_log.json`: scope decisions bound to this digest",
        "",
        "Do not render, send, or publish until every required scope has a fresh accepted decision.",
    ]
    return "\n".join(lines) + "\n"


def record_contribution(
    run_dir: Path,
    contribution_path: Path,
    *,
    provider: str,
    model: str,
    template_version: str,
    recorded_by: str,
    supersede: bool,
) -> Path:
    """Validate and record one contribution without overwriting history."""

    root = run_dir.resolve()
    with workflow_lock(root):
        return _record_contribution_locked(
            root,
            contribution_path,
            provider=provider,
            model=model,
            template_version=template_version,
            recorded_by=recorded_by,
            supersede=supersede,
        )


def _record_contribution_locked(
    root: Path,
    contribution_path: Path,
    *,
    provider: str,
    model: str,
    template_version: str,
    recorded_by: str,
    supersede: bool,
) -> Path:
    """Perform a contribution mutation while the run writer lock is held."""

    intake = load_json(root / "run_intake.json")
    source_register = load_json(root / "source_register.json")
    validate_input_integrity(root)
    contribution = load_json(contribution_path)
    intake_contract = {
        "run_id": intake["run_id"],
        "channels": intake["requested_channels"],
        "visual_requested": intake["visual_requested"],
        "history_inputs": source_register["history"],
    }
    validate_contribution_semantics(
        contribution,
        intake=intake_contract,
        source_register=source_register,
    )

    workbench_path = root / "content_workbench.json"
    previous = load_json(workbench_path) if workbench_path.is_file() else None
    if previous is not None and not supersede:
        raise ValueError(
            "Contribution already exists; use --supersede after professional return"
        )
    if previous is not None:
        review_log = load_json(root / "review_log.json")
        current_decisions = [
            row
            for row in review_log.get("events", [])
            if row.get("contribution_digest") == previous["contribution_digest"]
        ]
        if not any(
            row["decision"] in {"returned", "rejected"} for row in current_decisions
        ):
            raise ValueError(
                "Supersede requires a returned or rejected current contribution"
            )

    version = int(previous["version"]) + 1 if previous else 1
    provenance = {
        "provider": provider,
        "model": model,
        "template_version": template_version,
        "recorded_by": recorded_by,
        "recorded_at": utc_now(),
    }
    digest = canonical_digest(
        {
            "input_digest": intake["input_digest"],
            "contribution": contribution,
            "provenance": provenance,
        }
    )
    required_scopes = required_review_scopes(
        contribution,
        visual_requested=bool(intake["visual_requested"]),
    )
    post_generation_scopes = ["packaged_output"]
    if intake["visual_requested"] or "client_circular" in intake["requested_channels"]:
        post_generation_scopes.insert(0, "rendered_output")
    workbench = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "run_id": intake["run_id"],
        "version": version,
        "status": "proposed",
        "input_digest": intake["input_digest"],
        "contribution_digest": digest,
        "required_review_scopes": required_scopes,
        "post_generation_review_scopes": post_generation_scopes,
        "model_provenance": provenance,
        "contribution": contribution,
    }
    items = _review_items(contribution)
    review_payload = {
        "schema_version": "1.0",
        "plugin": "comunicazione-professionale",
        "workflow": "comunicazione-professionale",
        "run_id": intake["run_id"],
        "review_type": "professional_communication_review",
        "contribution_digest": digest,
        "required_review_scopes": required_scopes,
        "post_generation_review_scopes": post_generation_scopes,
        "items": items,
        "item_count": len(items),
        "status": "ready_for_review",
    }
    review_log_path = root / "review_log.json"
    review_log = (
        load_json(review_log_path)
        if review_log_path.is_file()
        else {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": intake["run_id"],
            "events": [],
        }
    )
    versions_dir = root / "versions"
    versions_dir.mkdir(exist_ok=True)
    version_path = versions_dir / f"content_workbench-v{version:03d}.json"
    atomic_write_json(root / "review_payload.json", review_payload)
    atomic_write_json(review_log_path, review_log)
    atomic_write_text(
        root / "review_handoff.md",
        _handoff_markdown(
            run_id=intake["run_id"],
            version=version,
            digest=digest,
            contribution=contribution,
            required_scopes=required_scopes,
            post_generation_scopes=post_generation_scopes,
        ),
    )
    atomic_write_json(version_path, workbench)
    atomic_write_json(workbench_path, workbench)
    return workbench_path


def main(argv: list[str] | None = None) -> int:
    """Record one model contribution."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--contribution", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--template-version", required=True)
    parser.add_argument("--recorded-by", required=True)
    parser.add_argument("--supersede", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = record_contribution(
            args.run_dir,
            args.contribution,
            provider=args.provider,
            model=args.model,
            template_version=args.template_version,
            recorded_by=args.recorded_by,
            supersede=args.supersede,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("CONTRIBUTION_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded contribution: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
