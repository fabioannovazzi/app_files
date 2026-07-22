"""Build a local Clara workbench for deck-revision interpretation."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from deck_revision_execution_contract import (
    CHANGE_SCOPES,
    EXECUTION_STRATEGIES,
    SUCCESS_CRITERION_TYPES,
    SUPPORTED_PATCH_OPERATIONS,
)

__all__ = [
    "DeckRevisionWorkbenchResult",
    "PLAN_SCHEMA",
    "build_deck_revision_workbench",
    "main",
]

LOGGER = logging.getLogger(__name__)

PLAN_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Clara deck revision changes",
    "type": "object",
    "required": ["schema_version", "source", "changes"],
    "properties": {
        "schema_version": {"const": 1},
        "source": {
            "type": "string",
            "description": "Set to codex_deck_revision_plan.",
        },
        "approved_for_pptx_revision": {
            "type": "boolean",
            "description": (
                "True only after the consultant or user approves the interpreted "
                "change list for PPTX editing."
            ),
            "default": False,
        },
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "slide_number",
                    "change_scope",
                    "change_type",
                    "requested_change",
                    "interpretation",
                    "rationale",
                    "explicitness",
                    "confidence",
                    "execution_strategy",
                    "transcript_evidence",
                    "visual_evidence",
                    "success_criteria",
                ],
                "properties": {
                    "change_id": {
                        "type": "string",
                        "description": "Stable local id such as chg-001.",
                    },
                    "slide_number": {"type": "integer", "minimum": 1},
                    "affected_slide_numbers": {
                        "type": "array",
                        "description": (
                            "Optional explicit slide set for global or clustered "
                            "edits. Defaults to slide_number when omitted."
                        ),
                        "items": {"type": "integer", "minimum": 1},
                    },
                    "slide_title": {"type": "string"},
                    "packet_scope": {
                        "enum": ["deck", "slide", "slide_cluster"],
                        "description": (
                            "Focused execution unit. Use deck for global changes "
                            "such as all-slide formatting or deck restructuring."
                        ),
                    },
                    "execution_group_id": {
                        "type": "string",
                        "description": (
                            "Optional stable id tying related changes into one "
                            "slide-cluster or deck packet."
                        ),
                    },
                    "dependency_change_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Other change ids that must be considered before or "
                            "with this change."
                        ),
                    },
                    "change_scope": {
                        "enum": sorted(CHANGE_SCOPES),
                        "description": (
                            "What kind of correction this is: exact text, layout, "
                            "visual object, storyline, deck structure, content, "
                            "or unknown."
                        ),
                    },
                    "change_type": {
                        "type": "string",
                        "description": (
                            "Short snake_case label, e.g. rewrite_headline, "
                            "delete_box, reorder_points, add_slide."
                        ),
                    },
                    "requested_change": {
                        "type": "string",
                        "description": (
                            "Consultant-readable instruction for what should "
                            "change on the deck."
                        ),
                    },
                    "interpretation": {
                        "type": "string",
                        "description": (
                            "Clara/Codex interpretation of what the speaker meant "
                            "in deck terms, separate from the raw request."
                        ),
                    },
                    "rationale": {
                        "type": "string",
                        "description": (
                            "Why this change follows from the call evidence and "
                            "deck context."
                        ),
                    },
                    "explicitness": {
                        "enum": ["explicit", "inferred", "uncertain"],
                        "description": (
                            "Whether the call explicitly requested the change or "
                            "Codex inferred it from context."
                        ),
                    },
                    "confidence": {"enum": ["high", "medium", "low"]},
                    "execution_strategy": {
                        "enum": sorted(EXECUTION_STRATEGIES),
                        "description": (
                            "How this change should be executed after approval: "
                            "deterministic patch, model-assisted edit, slide "
                            "rebuild, deck restructure, or human decision."
                        ),
                    },
                    "transcript_evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["quote"],
                            "properties": {
                                "speaker": {"type": "string"},
                                "timestamp_ms": {"type": "integer", "minimum": 0},
                                "quote": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "visual_evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["evidence_type", "note"],
                            "properties": {
                                "evidence_type": {
                                    "enum": [
                                        "deck_snapshot",
                                        "feedback_timeline",
                                        "video_frame",
                                        "screen_video",
                                        "manual_review",
                                    ]
                                },
                                "timestamp_ms": {"type": "integer", "minimum": 0},
                                "path": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "style_notes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "consultant_review_note": {"type": "string"},
                    "material_requirements": {
                        "type": "array",
                        "description": (
                            "Concrete missing materials or decisions needed before "
                            "execution, if any."
                        ),
                        "items": {"type": "string"},
                    },
                    "success_criteria": {
                        "type": "array",
                        "minItems": 1,
                        "description": (
                            "Checks that prove the requested change was executed. "
                            "Use mechanical criteria where possible and "
                            "semantic/manual criteria when judgement is required."
                        ),
                        "items": {
                            "type": "object",
                            "required": ["check_type", "description"],
                            "properties": {
                                "criterion_id": {"type": "string"},
                                "check_type": {"enum": sorted(SUCCESS_CRITERION_TYPES)},
                                "description": {"type": "string"},
                                "expected_text": {"type": "string"},
                                "absent_text": {"type": "string"},
                                "shape_index": {"type": "integer", "minimum": 1},
                                "expected_left": {"type": "integer"},
                                "expected_top": {"type": "integer"},
                                "expected_count": {"type": "integer", "minimum": 0},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "application_patches": {
                        "type": "array",
                        "description": (
                            "Optional deterministic PPTX patches. Include these "
                            "only when the intended edit is concrete enough to "
                            "apply without further judgement."
                        ),
                        "items": {
                            "type": "object",
                            "required": ["operation"],
                            "properties": {
                                "patch_id": {"type": "string"},
                                "operation": {
                                    "enum": sorted(SUPPORTED_PATCH_OPERATIONS)
                                },
                                "target": {
                                    "type": "object",
                                    "properties": {
                                        "shape_index": {
                                            "type": "integer",
                                            "minimum": 1,
                                        },
                                        "old_text": {"type": "string"},
                                        "expected_text": {"type": "string"},
                                    },
                                },
                                "value": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "old_text": {"type": "string"},
                                        "new_text": {"type": "string"},
                                        "left": {"type": "integer"},
                                        "top": {"type": "integer"},
                                        "width": {"type": "integer"},
                                        "height": {"type": "integer"},
                                        "expected_absent_text": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


@dataclass(frozen=True)
class DeckRevisionWorkbenchResult:
    """Artifacts created for Codex deck-revision interpretation."""

    session_dir: Path
    workbench_path: Path
    prompt_path: Path
    schema_path: Path
    review_path: Path


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseWorkspaceError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _relative_path(case_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(case_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _resolve_case_path(case_dir: Path, raw_path: str, *, label: str) -> Path:
    if not raw_path.strip():
        raise CaseWorkspaceError(f"{label} path is missing")
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    if not candidate.is_file():
        raise CaseWorkspaceError(f"{label} does not exist: {candidate}")
    return candidate.resolve()


def _resolve_optional_case_path(case_dir: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    return candidate.resolve() if candidate.is_file() else None


def _resolve_voice_session_dir(case_dir: Path, voice_session: Path | None) -> Path:
    sessions_root = case_dir / "voice_sessions"
    if voice_session is None:
        if not sessions_root.is_dir():
            raise CaseWorkspaceError("case has no voice_sessions folder")
        sessions = sorted(path for path in sessions_root.iterdir() if path.is_dir())
        if not sessions:
            raise CaseWorkspaceError("case has no imported voice sessions")
        return sessions[-1].resolve()

    candidate = voice_session.expanduser()
    candidates = (
        [candidate]
        if candidate.is_absolute()
        else [case_dir / candidate, sessions_root / candidate]
    )
    for path in candidates:
        if path.is_dir():
            resolved = path.resolve()
            try:
                resolved.relative_to(sessions_root.resolve())
            except ValueError as error:
                raise CaseWorkspaceError(
                    f"voice session must live under {sessions_root}: {resolved}"
                ) from error
            return resolved
    raise CaseWorkspaceError(f"voice session does not exist: {voice_session}")


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return _read_json(path)


def _require_status(
    payload: Mapping[str, Any],
    *,
    field: str,
    expected: str,
    missing_message: str,
) -> None:
    if payload.get("status") != expected:
        raise CaseWorkspaceError(missing_message)


def _slide_records(deck_snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_slide in deck_snapshot.get("slides", []):
        if not isinstance(raw_slide, dict):
            continue
        texts = raw_slide.get("texts", [])
        if not isinstance(texts, list):
            texts = []
        records.append(
            {
                "slide_number": raw_slide.get("slide_number"),
                "title": raw_slide.get("title") or "",
                "text_preview": [
                    str(text)
                    for text in texts[:8]
                    if isinstance(text, (str, int, float))
                ],
                "shape_count": (
                    len(raw_slide.get("shapes", []))
                    if isinstance(raw_slide.get("shapes"), list)
                    else None
                ),
            }
        )
    return records


def _render_prompt(
    *,
    workbench_rel: str,
    schema_rel: str,
    output_rel: str,
    review_rel: str,
) -> str:
    return "\n".join(
        [
            "# Clara Deck Revision Interpretation Prompt",
            "",
            "You are Codex/Clara preparing a deck-correction plan. The server only captured audio, transcript, and screen video. It did not decide what the partner meant.",
            "Semantic understanding of requested deck changes is Codex/Clara reasoning work. Do not replace it with deterministic rules, keyword matching, or mechanical slide matching.",
            "",
            "## Inputs",
            "",
            f"- Workbench JSON: `{workbench_rel}`",
            f"- Required output schema: `{schema_rel}`",
            f"- Write the interpreted change plan to: `{output_rel}`",
            f"- After writing the JSON, run the finalizer to render: `{review_rel}`",
            "",
            "## Task",
            "",
            "1. First run `build_deck_revision_interpretation_packets.py` and use the packet JSON/Markdown files as the focused semantic inputs; use the workbench as an index, not as one huge interpretation prompt.",
            "2. Treat this invocation as the local deck-revision workflow. If the evidence clearly contradicts that, write an empty `changes` list and explain the reason in `open_questions`.",
            "3. Use the attributed transcript as the semantic source for what was requested.",
            "4. Use feedback timeline frames, screen video references, and the deck snapshot only to ground which slide or visible object the transcript is about.",
            "5. Treat feedback timeline `slide_match` fields as deterministic slide candidates only. Use high/medium matches as grounding evidence when the visible frame agrees with the deck snapshot; treat low/no matches as navigation hints.",
            "6. Use the PPTX deck snapshot and the resolved deck style spec as the deck/style authorities.",
            "7. Use advisory-output-shaper behavior for advisory/family/governance wording: make the instructions useful, evidence-aware, room-safe, and not a raw transcript paste.",
            "8. Distinguish explicit requests from inferred implications.",
            "9. For every change, write both the raw requested change and Clara's interpreted deck meaning.",
            "10. Assign one execution strategy: `deterministic_patch`, `model_assisted_edit`, `slide_rebuild`, `deck_restructure`, or `needs_human_decision`.",
            "10a. Assign the focused execution unit with `packet_scope`: `slide` for local edits, `slide_cluster` for related slides, or `deck` for global changes such as all-slide font changes, deck sequence, or added/removed slides. Use `affected_slide_numbers`, `execution_group_id`, and `dependency_change_ids` when needed.",
            "11. Add success criteria for every change. Use mechanical checks such as title/text/position when possible; use `semantic_review` or `manual_review` when the change cannot be proved mechanically.",
            "12. Do not invent unseen deck content, unmentioned business facts, or fake timestamps.",
            "13. Do not edit the PPTX in this step.",
            "14. If the change is concrete enough for deterministic PPTX editing, set `execution_strategy` to `deterministic_patch` and add `application_patches`; otherwise state the model/human/rebuild route and any material requirements.",
            "15. For every patch that edits an existing slide object, include `target.expected_text` from the current deck snapshot so apply can block stale or wrong-object edits.",
            "16. Keep deterministic logic limited to evidence preparation, schema validation, patch execution, and verification. It must not decide what the partner meant.",
            "17. If a change asks for better quotes, interview evidence, transcript excerpts, or source-backed examples for a slide, add a material requirement for `deck_revision_quote_candidate_matrix.json`; Clara/Codex must build and review that matrix before selecting quotes or editing the PPTX.",
            "",
            "## Output",
            "",
            "Write one JSON object matching the schema. Each change must be readable by a consultant without opening the JSON source files: it needs the slide number, what should change, Clara's interpretation, why, confidence, explicitness, execution strategy, success criteria, and evidence references. For automatic application, each executable patch must name a supported operation and concrete target/value fields. Existing-object patches must bind to both `shape_index` where relevant and `target.expected_text` from the pre-edit deck.",
            "",
        ]
    )


def _render_review(
    *,
    workbench: Mapping[str, Any],
    output_rel: str,
    review_rel: str,
) -> str:
    deck = workbench["deck"]
    source_paths = workbench["source_paths"]
    style = workbench["deck_style"]
    lines = [
        "# Deck Revision Workbench",
        "",
        "Status: the local workbench is ready for Codex interpretation. No PPTX edits have been made.",
        "",
        "## Inputs",
        "",
        f"- Case: `{workbench['case']['case_dir']}`",
        f"- Voice session: `{workbench['voice_session']}`",
        f"- Deck: `{deck['path']}`",
        f"- Deck snapshot: `{source_paths['deck_snapshot_path']}`",
        f"- Attributed transcript: `{source_paths['attributed_transcript_path']}`",
        f"- Feedback timeline: `{source_paths.get('feedback_timeline_path') or 'not available'}`",
        f"- Screen video: `{source_paths.get('screen_video_path') or 'not available'}`",
        f"- Deck style: `{style.get('style_name') or style.get('style_key')}`",
        f"- Deck style spec: `{source_paths['deck_style_spec_path']}`",
        f"- Advisory method: `{workbench['advisory_method']['skill']}`",
        "",
        "## Required Next Artifact",
        "",
        f"- Codex/model-authored change JSON: `{output_rel}`",
        f"- Consultant-readable rendered list: `{review_rel}`",
        f"- Interpretation packets: `{source_paths['interpretation_packets_path']}`",
        f"- Execution packets after approval/routing: `{source_paths['execution_packets_path']}`",
        "",
        "## Rules",
        "",
        "- The change list is the consultant checkpoint: it says what Clara understood should change.",
        "- Build and use interpretation packets before writing the change list; the full workbench is an index, not the semantic prompt.",
        "- The execution strategy says how each approved change will be attempted: patch, model-assisted edit, rebuild, restructure, or human decision.",
        "- Use packet_scope/affected_slide_numbers/execution_group_id so execution happens slide-by-slide, by slide cluster, or by deck-level packet.",
        "- Success criteria are mandatory; they are how the corrected deck will be checked.",
        "- PPTX editing starts only after the change list is reviewed or explicitly approved.",
        "- Each change must keep transcript evidence separate from visual/deck evidence.",
        "- Inferred changes must be marked as inferred or uncertain, not presented as partner instructions.",
        "",
    ]
    return "\n".join(lines)


def build_deck_revision_workbench(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionWorkbenchResult:
    """Build the local workbench for a Codex-authored deck change plan."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    intake_path = session_dir / "deck_revision_intake.json"
    if not intake_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision intake is missing: {intake_path}; run prepare_voice_deck_revision.py first"
        )
    intake = _read_json(intake_path)

    speaker = intake.get("speaker_attribution")
    if not isinstance(speaker, dict):
        raise CaseWorkspaceError("deck revision intake is missing speaker attribution")
    _require_status(
        speaker,
        field="speaker_attribution",
        expected="available",
        missing_message=(
            "speaker-attributed transcript is required before building the "
            "deck revision workbench"
        ),
    )

    deck = intake.get("deck")
    if not isinstance(deck, dict):
        raise CaseWorkspaceError("deck revision intake is missing deck metadata")
    _require_status(
        deck,
        field="deck",
        expected="attached",
        missing_message=(
            "attached PPTX deck is required before building the deck revision workbench"
        ),
    )

    deck_style = intake.get("deck_style")
    if not isinstance(deck_style, dict):
        raise CaseWorkspaceError("deck revision intake is missing deck style metadata")
    _require_status(
        deck_style,
        field="deck_style",
        expected="available",
        missing_message=(
            "resolved deck style authority is required before building the "
            "deck revision workbench"
        ),
    )

    advisory_method = intake.get("advisory_method")
    if not isinstance(advisory_method, dict):
        raise CaseWorkspaceError("deck revision intake is missing advisory method")

    attributed_transcript_path = _resolve_case_path(
        case_dir,
        str(speaker.get("attributed_transcript_path") or ""),
        label="attributed transcript",
    )
    deck_snapshot_path = _resolve_case_path(
        case_dir,
        str(deck.get("snapshot_path") or ""),
        label="deck snapshot",
    )
    deck_path = _resolve_case_path(
        case_dir,
        str(deck.get("path") or ""),
        label="PPTX deck",
    )
    style_spec_path = _resolve_case_path(
        case_dir,
        str(deck_style.get("snapshot_path") or deck_style.get("spec_path") or ""),
        label="deck style spec",
    )

    evidence = intake.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    feedback_timeline_path = _resolve_optional_case_path(
        case_dir,
        evidence.get("feedback_timeline_path"),
    )
    video_timeline_path = _resolve_optional_case_path(
        case_dir,
        evidence.get("video_timeline_path"),
    )
    screen_video_path = _resolve_optional_case_path(
        case_dir,
        evidence.get("screen_video_path"),
    )
    raw_transcript_path = _resolve_optional_case_path(
        case_dir,
        evidence.get("raw_transcript_path"),
    )
    company_profile_path = _resolve_optional_case_path(
        case_dir,
        (
            intake.get("company_profile", {}).get("path")
            if isinstance(intake.get("company_profile"), dict)
            else None
        ),
    )

    deck_snapshot = _read_json(deck_snapshot_path)
    feedback_timeline = _load_optional_json(feedback_timeline_path)
    video_timeline = _load_optional_json(video_timeline_path)
    attributed_transcript_text = attributed_transcript_path.read_text(encoding="utf-8")
    style_spec_text = style_spec_path.read_text(encoding="utf-8")
    case_manifest = _read_json(case_dir / "case_manifest.json")

    workbench_path = session_dir / "deck_revision_workbench.json"
    prompt_path = session_dir / "deck_revision_prompt.md"
    schema_path = session_dir / "deck_revision_changes.schema.json"
    output_path = session_dir / "deck_revision_changes.json"
    review_path = session_dir / "deck_revision_changes.md"
    understanding_path = session_dir / "deck_revision_understanding.md"
    execution_plan_path = session_dir / "deck_revision_execution_plan.json"
    execution_review_path = session_dir / "deck_revision_execution_plan.md"
    interpretation_packets_path = (
        session_dir / "deck_revision_interpretation_packets.json"
    )
    interpretation_packets_review_path = (
        session_dir / "deck_revision_interpretation_packets.md"
    )
    execution_packets_path = session_dir / "deck_revision_execution_packets.json"
    execution_packets_review_path = session_dir / "deck_revision_execution_packets.md"

    workbench: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_workbench",
        "created_at": _now_iso(now),
        "voice_session": _relative_path(case_dir, session_dir),
        "case": {
            "case_dir": _relative_path(case_dir, case_dir),
            "manifest": case_manifest,
            "company_profile_path": (
                _relative_path(case_dir, company_profile_path)
                if company_profile_path is not None
                else None
            ),
        },
        "status": {
            "case_context": "available",
            "speaker_attribution": "available",
            "deck": "attached",
            "deck_snapshot": "available",
            "deck_style": "available",
            "advisory_method": "available",
            "pptx_edits_made": False,
        },
        "source_paths": {
            "intake_path": _relative_path(case_dir, intake_path),
            "gate_path": _relative_path(
                case_dir, session_dir / "deck_revision_gate.md"
            ),
            "raw_transcript_path": (
                _relative_path(case_dir, raw_transcript_path)
                if raw_transcript_path is not None
                else None
            ),
            "attributed_transcript_path": _relative_path(
                case_dir, attributed_transcript_path
            ),
            "feedback_timeline_path": (
                _relative_path(case_dir, feedback_timeline_path)
                if feedback_timeline_path is not None
                else None
            ),
            "video_timeline_path": (
                _relative_path(case_dir, video_timeline_path)
                if video_timeline_path is not None
                else None
            ),
            "screen_video_path": (
                _relative_path(case_dir, screen_video_path)
                if screen_video_path is not None
                else None
            ),
            "deck_path": _relative_path(case_dir, deck_path),
            "deck_snapshot_path": _relative_path(case_dir, deck_snapshot_path),
            "deck_style_spec_path": _relative_path(case_dir, style_spec_path),
            "changes_schema_path": _relative_path(case_dir, schema_path),
            "changes_output_path": _relative_path(case_dir, output_path),
            "changes_review_path": _relative_path(case_dir, review_path),
            "understanding_path": _relative_path(case_dir, understanding_path),
            "interpretation_packets_path": _relative_path(
                case_dir, interpretation_packets_path
            ),
            "interpretation_packets_review_path": _relative_path(
                case_dir, interpretation_packets_review_path
            ),
            "execution_plan_path": _relative_path(case_dir, execution_plan_path),
            "execution_review_path": _relative_path(case_dir, execution_review_path),
            "execution_packets_path": _relative_path(case_dir, execution_packets_path),
            "execution_packets_review_path": _relative_path(
                case_dir, execution_packets_review_path
            ),
        },
        "deck": {
            "path": _relative_path(case_dir, deck_path),
            "material_id": deck.get("material_id"),
            "slide_count": deck_snapshot.get("slide_count"),
            "slides": _slide_records(deck_snapshot),
            "editable_merge_input": deck.get("editable_merge_input"),
        },
        "deck_style": deck_style,
        "advisory_method": advisory_method,
        "transcript": {
            "attributed_transcript_text": attributed_transcript_text,
            "speaker_attribution_source": speaker.get("source"),
        },
        "visual_context": {
            "feedback_timeline": feedback_timeline,
            "video_timeline": video_timeline,
            "screen_video_available": screen_video_path is not None,
        },
        "style_spec_text": style_spec_text,
        "plan_schema": PLAN_SCHEMA,
        "interpretation_rules": [
            "Use transcript text for what was said.",
            "Use Codex/Clara reasoning, not deterministic rules, to understand requested deck changes.",
            "Use video/timeline/deck context to identify the visible slide or object.",
            "Do not edit the PPTX while building the change list.",
            "Separate explicit partner requests from Codex inference.",
            "Use advisory-output-shaper behavior for advisory wording.",
            "Apply the resolved deck style spec to any future slide edits.",
        ],
    }

    _write_json(schema_path, PLAN_SCHEMA)
    _write_json(workbench_path, workbench)
    prompt_path.write_text(
        _render_prompt(
            workbench_rel=_relative_path(case_dir, workbench_path),
            schema_rel=_relative_path(case_dir, schema_path),
            output_rel=_relative_path(case_dir, output_path),
            review_rel=_relative_path(case_dir, review_path),
        ),
        encoding="utf-8",
    )
    review_path.write_text(
        _render_review(
            workbench=workbench,
            output_rel=_relative_path(case_dir, output_path),
            review_rel=_relative_path(case_dir, review_path),
        ),
        encoding="utf-8",
    )

    return DeckRevisionWorkbenchResult(
        session_dir=session_dir,
        workbench_path=workbench_path,
        prompt_path=prompt_path,
        schema_path=schema_path,
        review_path=review_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a Clara deck-revision workbench from a prepared voice session.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--voice-session",
        type=Path,
        default=None,
        help="Voice session folder name/path. Defaults to latest voice session.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_deck_revision_workbench(
        args.case_dir,
        voice_session=args.voice_session,
    )
    LOGGER.info("wrote deck revision workbench to %s", result.workbench_path)
    LOGGER.info("wrote deck revision prompt to %s", result.prompt_path)
    LOGGER.info("wrote deck revision schema to %s", result.schema_path)
    LOGGER.info("wrote deck revision review stub to %s", result.review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
