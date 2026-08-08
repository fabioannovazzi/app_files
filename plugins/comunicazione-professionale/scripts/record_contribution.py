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
    validate_answer_contract,
    validate_claim_assurance,
    validate_contribution_semantics,
    validate_input_integrity,
    validate_schema,
    verify_editorial_assessor_qualification,
    workflow_lock,
)

__all__ = ["record_contribution", "main"]

LOGGER = logging.getLogger(__name__)


def _review_items(
    contribution: dict[str, Any],
    answer_contract: dict[str, Any],
    claim_assurance: dict[str, Any],
    editorial_assessment: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "id": "answer-contract",
            "item_type": "answer_contract",
            "title": "Question-to-validated-answer contract",
            "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
            "recommended_action": "mark_unclear",
            "data": answer_contract,
            "evidence": [],
        },
        {
            "id": "claim-assurance",
            "item_type": "claim_assurance",
            "title": "Independent source-support and reasoning review",
            "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
            "recommended_action": "mark_unclear",
            "data": claim_assurance,
            "evidence": [],
        },
        {
            "id": "editorial-assessment",
            "item_type": "editorial_assessment",
            "title": "Independent editorial challenge",
            "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
            "recommended_action": "mark_unclear",
            "data": editorial_assessment,
            "evidence": [],
        },
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
        },
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
    if contribution["recommendation"] == "publish":
        visual_story = contribution["visual_story"]
        items.append(
            {
                "id": "visual-story",
                "item_type": "visual_story",
                "title": (
                    visual_story["title"]
                    if visual_story["decision"] == "render"
                    else "Visual recommendation: omit"
                ),
                "allowed_actions": ["accept", "reject", "edit", "mark_unclear"],
                "recommended_action": "edit",
                "data": visual_story,
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
        "## Visual decision",
        "",
        f"- Decision: **{contribution['visual_story']['decision']}**",
        f"- Reason: {contribution['visual_story']['decision_reason']}",
        f"- Incremental value over channel copy: {contribution['visual_story']['incremental_value'] or 'none'}",
        "",
        "Reject a visual story that merely splits or paraphrases the post, uses a large number without decision value, repeats the same proposition across title/highlight/body, exposes internal source IDs, repeats Studio identity without an approved convention, or presents a preliminary checklist as sufficient for a professional conclusion.",
        "",
        "## Review files",
        "",
        "- `source_register.json`: exact input snapshots and hashes",
        "- `content_workbench.json`: answer contract, claim assurance, contribution, editorial assessment, and provenance",
        "- `review_payload.json`: item-level review queue",
        "- `review_log.json`: scope decisions bound to this digest",
        "",
        "Do not render, send, or publish until every required scope has a fresh accepted decision.",
    ]
    return "\n".join(lines) + "\n"


def record_contribution(
    run_dir: Path,
    contribution_path: Path,
    answer_contract_path: Path,
    claim_assurance_path: Path,
    editorial_assessment_path: Path,
    *,
    provider: str,
    model: str,
    template_version: str,
    recorded_by: str,
    assessment_provider: str,
    assessment_model: str,
    claim_assessment_provider: str,
    claim_assessment_model: str,
    supersede: bool,
) -> Path:
    """Validate and record one contribution without overwriting history."""

    root = run_dir.resolve()
    with workflow_lock(root):
        return _record_contribution_locked(
            root,
            contribution_path,
            answer_contract_path,
            claim_assurance_path,
            editorial_assessment_path,
            provider=provider,
            model=model,
            template_version=template_version,
            recorded_by=recorded_by,
            assessment_provider=assessment_provider,
            assessment_model=assessment_model,
            claim_assessment_provider=claim_assessment_provider,
            claim_assessment_model=claim_assessment_model,
            supersede=supersede,
        )


def _record_contribution_locked(
    root: Path,
    contribution_path: Path,
    answer_contract_path: Path,
    claim_assurance_path: Path,
    editorial_assessment_path: Path,
    *,
    provider: str,
    model: str,
    template_version: str,
    recorded_by: str,
    assessment_provider: str,
    assessment_model: str,
    claim_assessment_provider: str,
    claim_assessment_model: str,
    supersede: bool,
) -> Path:
    """Perform a contribution mutation while the run writer lock is held."""

    intake = load_json(root / "run_intake.json")
    source_register = load_json(root / "source_register.json")
    validate_input_integrity(root)
    contribution = load_json(contribution_path)
    answer_contract = load_json(answer_contract_path)
    claim_assurance = load_json(claim_assurance_path)
    editorial_assessment = load_json(editorial_assessment_path)
    validate_schema(editorial_assessment, "editorial_assessment.schema.json")
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
    answer_contract_digest = validate_answer_contract(
        answer_contract,
        intake={
            "run_id": intake["run_id"],
            "audience": intake["audience"],
            "language": intake["language"],
            "jurisdiction": intake["jurisdiction"],
        },
    )
    raw_contribution_digest = canonical_digest(contribution)
    validate_claim_assurance(
        claim_assurance,
        contribution=contribution,
        answer_contract_digest=answer_contract_digest,
        source_register=source_register,
    )
    claim_assurance_digest = canonical_digest(claim_assurance)
    if editorial_assessment["run_id"] != contribution["run_id"]:
        raise ValueError("Editorial assessment run_id does not match contribution")
    if editorial_assessment["assessed_contribution_digest"] != raw_contribution_digest:
        raise ValueError("Editorial assessment is stale for this contribution")
    if editorial_assessment["claim_assurance_digest"] != claim_assurance_digest:
        raise ValueError("Editorial assessment is stale for claim assurance")
    protocol = editorial_assessment["assessment_protocol"]
    if (
        protocol["assessment_template_version"]
        != "professional-communication-editorial-v3"
    ):
        raise ValueError("Unsupported editorial assessment template")
    workspace = Path(intake["workspace_path"]).resolve()
    qualification = verify_editorial_assessor_qualification(
        workspace,
        provider=assessment_provider,
        model=assessment_model,
        template_version=protocol["assessment_template_version"],
    )
    if (
        protocol["assessor_session_id"]
        == qualification["assessor_identity"]["assessor_session_id"]
    ):
        raise ValueError(
            "Live editorial assessment must use a session separate from qualification"
        )
    if editorial_assessment["verdict"] != "ready":
        raise ValueError(
            "Editorial assessment must be ready before contribution recording"
        )
    if (
        editorial_assessment["visual_verdict"]
        != contribution["visual_story"]["decision"]
    ):
        raise ValueError(
            "Editorial assessment visual verdict disagrees with contribution"
        )
    channel_assessments = editorial_assessment["channel_assessments"]
    expected_channels = [draft["channel"] for draft in contribution["channel_drafts"]]
    assessed_channels = [row["channel"] for row in channel_assessments]
    if len(assessed_channels) != len(set(assessed_channels)):
        raise ValueError("Editorial assessment repeats a channel verdict")
    if set(assessed_channels) != set(expected_channels):
        raise ValueError(
            "Editorial assessment must cover every contribution channel exactly"
        )
    if any(row["verdict"] != "ready" for row in channel_assessments):
        raise ValueError("Editorial assessment contains a non-ready channel verdict")
    slide_assessments = editorial_assessment["slide_assessments"]
    expected_slide_indices = list(
        range(1, len(contribution["visual_story"]["slides"]) + 1)
    )
    assessed_slide_indices = [row["slide_index"] for row in slide_assessments]
    if assessed_slide_indices != expected_slide_indices:
        raise ValueError(
            "Editorial assessment must cover visual slides once and in order"
        )
    if any(row["verdict"] in {"weak", "redundant"} for row in slide_assessments):
        raise ValueError(
            "Editorial assessment contains a weak or redundant visual slide"
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
    recorded_at = utc_now()
    provenance = {
        "generator": {
            "provider": provider,
            "model": model,
            "template_version": template_version,
        },
        "editorial_assessor": {
            "provider": assessment_provider,
            "model": assessment_model,
            "template_version": protocol["assessment_template_version"],
            "assessor_session_id": protocol["assessor_session_id"],
            "qualification_digest": qualification["qualification_digest"],
        },
        "claim_assessor": {
            "provider": claim_assessment_provider,
            "model": claim_assessment_model,
            "template_version": "professional-communication-claim-assurance-v1",
        },
        "recorded_by": recorded_by,
        "recorded_at": recorded_at,
    }
    digest = canonical_digest(
        {
            "input_digest": intake["input_digest"],
            "contribution": contribution,
            "answer_contract": answer_contract,
            "claim_assurance": claim_assurance,
            "editorial_assessment": editorial_assessment,
            "provenance": provenance,
        }
    )
    required_scopes = required_review_scopes(
        contribution,
        visual_requested=bool(intake["visual_requested"]),
    )
    post_generation_scopes = ["packaged_output"]
    if (
        contribution["visual_story"]["slides"]
        or "client_circular" in intake["requested_channels"]
    ):
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
        "answer_contract": answer_contract,
        "claim_assurance": claim_assurance,
        "editorial_assessment": editorial_assessment,
        "contribution": contribution,
    }
    items = _review_items(
        contribution,
        answer_contract,
        claim_assurance,
        editorial_assessment,
    )
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
    parser.add_argument("--answer-contract", type=Path, required=True)
    parser.add_argument("--claim-assurance", type=Path, required=True)
    parser.add_argument("--editorial-assessment", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--template-version", required=True)
    parser.add_argument("--recorded-by", required=True)
    parser.add_argument("--assessment-provider", required=True)
    parser.add_argument("--assessment-model", required=True)
    parser.add_argument("--claim-assessment-provider", required=True)
    parser.add_argument("--claim-assessment-model", required=True)
    parser.add_argument("--supersede", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = record_contribution(
            args.run_dir,
            args.contribution,
            args.answer_contract,
            args.claim_assurance,
            args.editorial_assessment,
            provider=args.provider,
            model=args.model,
            template_version=args.template_version,
            recorded_by=args.recorded_by,
            assessment_provider=args.assessment_provider,
            assessment_model=args.assessment_model,
            claim_assessment_provider=args.claim_assessment_provider,
            claim_assessment_model=args.claim_assessment_model,
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
