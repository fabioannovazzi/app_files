#!/usr/bin/env python3
"""Prepare a digest-bound, non-publishable Creative Production handoff."""

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
    recompute_contribution_digest,
    utc_now,
    validate_input_integrity,
    validate_schema,
    workflow_lock,
)

__all__ = ["prepare_creative_direction_handoff", "main"]

LOGGER = logging.getLogger(__name__)


def _studio_visual_context(
    intake: dict[str, Any],
    contribution: dict[str, Any],
    source_register: dict[str, Any],
) -> dict[str, Any]:
    proposal = contribution.get("studio_profile_proposal")
    if proposal is not None:
        profile = proposal
        profile_status = "unreviewed_run_profile_proposal"
    else:
        stored = intake.get("studio_profile")
        if not isinstance(stored, dict) or not isinstance(stored.get("payload"), dict):
            raise ValueError("A stored or proposed studio profile is required")
        profile = stored["payload"]["profile"]
        profile_status = "stored_approved_profile"

    brand = intake["brand_profile"]
    logo = source_register.get("brand_logo")
    logo_record = {
        "present": isinstance(logo, dict),
        "snapshot_path": (
            str(logo.get("snapshot_path", "")) if isinstance(logo, dict) else ""
        ),
        "sha256": str(logo.get("sha256", "")) if isinstance(logo, dict) else "",
    }
    social = profile["social"]
    return {
        "profile_status": profile_status,
        "brand": {
            key: brand[key]
            for key in (
                "studio_name",
                "primary_color",
                "accent_color",
                "background_color",
                "text_color",
            )
        },
        "social": {
            key: social[key]
            for key in (
                "preferred_format",
                "carousel_identity_placement",
                "show_source_note",
            )
        },
        "logo": logo_record,
    }


def _exact_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "kind",
        "layout_variant",
        "eyebrow",
        "title",
        "body",
        "bullets",
        "highlight",
        "source_note",
        "reader_use",
        "relationship_to_post",
    )
    exact: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        content = {key: slide[key] for key in fields}
        exact.append(
            {
                "slide_index": index,
                **content,
                "content_digest": canonical_digest(content),
            }
        )
    return exact


def _handoff_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Optional Creative Production direction handoff",
        "",
        "This is a non-publishable art-direction brief. Vera owns exact content, identity, deterministic rendering, and final QA.",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Contribution: `{payload['binding']['contribution_digest']}`",
        f"- Requested distinct directions: {payload['production_request']['direction_count']}",
        "- Final format: 1080 × 1350 px",
        "- Human selection required: yes",
        "",
        "## Creative Production instruction",
        "",
        "Create genuinely distinct editorial art-direction references. Use the locked copy only to understand hierarchy and information density. Do not render final text, data, source notes, Studio identity, or a synthetic logo into the references. Keep viable safe areas for Vera's deterministic live typography. The board output is a design reference, never a publishable slide.",
        "",
        "## Locked exact content",
        "",
    ]
    for slide in payload["exact_content"]:
        lines.extend(
            [
                f"### Slide {slide['slide_index']} · {slide['kind']}",
                "",
                f"- Layout proposal: `{slide['layout_variant']}`",
                f"- Eyebrow: {slide['eyebrow']}",
                f"- Title: {slide['title']}",
                f"- Body: {slide['body']}",
                f"- Bullets: {' | '.join(slide['bullets']) or '—'}",
                f"- Highlight: {slide['highlight'] or '—'}",
                f"- Public source note: {slide['source_note'] or '—'}",
                f"- Reader use: {slide['reader_use']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Non-negotiable boundary",
            "",
            "The selected direction must be translated back into Vera's reviewed visual story and deterministic renderer. It cannot add facts, rewrite copy, change numbers or dates, fabricate diagrams, alter the logo, or bypass the model-led and professional review gates.",
            "",
        ]
    )
    return "\n".join(lines)


def prepare_creative_direction_handoff(
    run_dir: Path,
    *,
    direction_count: int = 4,
) -> Path:
    """Write exact handoff data; creative quality remains a model-led judgment."""

    root = run_dir.resolve()
    with workflow_lock(root):
        validate_input_integrity(root)
        intake = load_json(root / "run_intake.json")
        route = intake["external_routes"]["creative_production"]
        if not route["selected"]:
            raise ValueError(
                "Creative Production was not explicitly selected in the run intake"
            )
        if not 4 <= direction_count <= 6:
            raise ValueError("Creative Production requires four to six directions")

        workbench = load_json(root / "content_workbench.json")
        contribution_digest = recompute_contribution_digest(root)
        contribution = workbench["contribution"]
        story = contribution["visual_story"]
        if contribution["recommendation"] != "publish":
            raise ValueError("No creative direction handoff for no_publish")
        if story["decision"] != "render" or not story["slides"]:
            raise ValueError(
                "Creative direction requires an editorially accepted render story"
            )

        source_register = load_json(root / "source_register.json")
        payload = {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": intake["run_id"],
            "contribution_version": workbench["version"],
            "created_at": utc_now(),
            "status": "ready_for_optional_creative_direction",
            "binding": {
                "input_digest": workbench["input_digest"],
                "contribution_digest": contribution_digest,
                "visual_story_digest": canonical_digest(story),
            },
            "route": {
                "plugin": "creative-production",
                "skill": "creative-production:produce",
                "board_tool": "creative_production_board",
                "destination": route["destination"],
                "approved_by": route["approved_by"],
                "approved_at": route["approved_at"],
            },
            "studio_visual_context": _studio_visual_context(
                intake, contribution, source_register
            ),
            "production_request": {
                "direction_count": direction_count,
                "target_width_px": 1080,
                "target_height_px": 1350,
                "output_kind": "art_direction_references",
                "publishable": False,
                "human_selection_required": True,
                "final_renderer": "vera_deterministic_renderer",
            },
            "exact_content": _exact_slides(story["slides"]),
            "content_locks": [
                "eyebrow",
                "title",
                "body",
                "bullets",
                "highlight",
                "dates_and_numbers",
                "public_source_note",
                "studio_name_and_logo",
            ],
            "allowed_exploration": [
                "composition",
                "hierarchy",
                "spacing_rhythm",
                "rules_and_shapes",
                "brand_constrained_color_balance",
                "non_factual_texture",
            ],
            "prohibited_output": [
                "publishable_final_slide",
                "rewritten_or_rasterized_exact_copy",
                "new_factual_or_legal_claim",
                "invented_chart_or_data",
                "synthetic_or_altered_logo",
                "repeated_studio_identity_outside_profile_rule",
            ],
            "fallback": {
                "when_unavailable": "use_internal_visual_system",
                "renderer": "vera_deterministic_renderer",
                "run_must_continue": True,
            },
        }
        payload["handoff_digest"] = canonical_digest(payload)
        validate_schema(payload, "creative_direction_handoff.schema.json")

        output_dir = root / "creative-direction"
        json_path = output_dir / f"handoff-v{workbench['version']:03d}.json"
        markdown_path = output_dir / f"handoff-v{workbench['version']:03d}.md"
        if json_path.exists() or markdown_path.exists():
            raise ValueError(
                "Creative direction handoff already exists for this contribution version"
            )
        atomic_write_json(json_path, payload)
        atomic_write_text(markdown_path, _handoff_markdown(payload))
        return json_path


def main(argv: list[str] | None = None) -> int:
    """Prepare one optional Creative Production handoff."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--directions", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        path = prepare_creative_direction_handoff(
            args.run_dir, direction_count=args.directions
        )
    except (OSError, ValueError, KeyError) as exc:
        LOGGER.error("CREATIVE_DIRECTION_HANDOFF_FAILED: %s", exc)
        return 1
    LOGGER.info("Prepared optional Creative Production handoff: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
