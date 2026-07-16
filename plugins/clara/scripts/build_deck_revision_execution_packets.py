"""Build focused Clara deck-revision execution packets."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace

__all__ = [
    "DeckRevisionExecutionPacketsResult",
    "build_deck_revision_execution_packets",
    "main",
]

LOGGER = logging.getLogger(__name__)
PACKET_SCOPES = {"slide", "slide_cluster", "deck"}


@dataclass(frozen=True)
class DeckRevisionExecutionPacketsResult:
    """Artifacts created for focused deck-revision execution."""

    session_dir: Path
    packet_index_path: Path
    review_path: Path
    packet_dir: Path


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseWorkspaceError(f"expected JSON object in {path}")
    return payload


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_json(path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _relative_path(case_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(case_dir.resolve()))
    except ValueError:
        return str(path.resolve())


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


def _load_plan(
    session_dir: Path, plan_path: Path | None, case_dir: Path
) -> tuple[Path, dict[str, Any]]:
    candidate = plan_path or (session_dir / "deck_revision_changes.normalized.json")
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    if not candidate.is_file():
        raise CaseWorkspaceError(
            f"normalized deck revision plan is missing: {candidate}; run finalize_deck_revision_plan.py first"
        )
    return candidate.resolve(), _read_json(candidate)


def _required_workbench(session_dir: Path) -> dict[str, Any]:
    workbench_path = session_dir / "deck_revision_workbench.json"
    if not workbench_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision workbench is missing: {workbench_path}; run build_deck_revision_workbench.py first"
        )
    return _read_json(workbench_path)


def _slide_records(workbench: Mapping[str, Any]) -> list[dict[str, Any]]:
    deck = workbench.get("deck")
    if not isinstance(deck, Mapping):
        raise CaseWorkspaceError("deck revision workbench is missing deck metadata")
    slides: list[dict[str, Any]] = []
    for slide in deck.get("slides", []):
        if isinstance(slide, dict) and isinstance(slide.get("slide_number"), int):
            slides.append(dict(slide))
    if not slides:
        raise CaseWorkspaceError("deck revision workbench has no slide records")
    return slides


def _deck_outline(slides: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "slide_number": slide.get("slide_number"),
            "title": slide.get("title") or "",
        }
        for slide in slides
    ]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _affected_slide_numbers(
    change: Mapping[str, Any], slide_lookup: Mapping[int, Mapping[str, Any]]
) -> list[int]:
    raw_numbers = change.get("affected_slide_numbers")
    numbers: list[int] = []
    if isinstance(raw_numbers, list):
        for item in raw_numbers:
            if isinstance(item, int) and not isinstance(item, bool):
                numbers.append(item)
    if not numbers and isinstance(change.get("slide_number"), int):
        numbers.append(int(change["slide_number"]))
    seen: set[int] = set()
    valid_numbers: list[int] = []
    for number in numbers:
        if number not in slide_lookup or number in seen:
            continue
        valid_numbers.append(number)
        seen.add(number)
    if not valid_numbers:
        raise CaseWorkspaceError(
            f"{change.get('change_id') or 'change'}: no valid affected slide numbers"
        )
    return valid_numbers


def _has_slide_count_criterion(change: Mapping[str, Any]) -> bool:
    criteria = change.get("success_criteria")
    if not isinstance(criteria, list):
        return False
    return any(
        isinstance(item, Mapping) and item.get("check_type") == "slide_count_equals"
        for item in criteria
    )


def _packet_scope(change: Mapping[str, Any], affected_slide_numbers: list[int]) -> str:
    explicit_scope = str(change.get("packet_scope") or "").strip()
    if explicit_scope in PACKET_SCOPES:
        return explicit_scope
    if (
        change.get("execution_strategy") == "deck_restructure"
        or change.get("change_scope") == "structure"
        or _has_slide_count_criterion(change)
    ):
        return "deck"
    if len(affected_slide_numbers) > 1 or str(change.get("execution_group_id") or ""):
        return "slide_cluster"
    return "slide"


def _group_key(
    change: Mapping[str, Any], packet_scope: str, affected_slide_numbers: list[int]
) -> str:
    group_id = str(change.get("execution_group_id") or "").strip()
    if packet_scope == "deck":
        return f"deck:{group_id or 'deck'}"
    if packet_scope == "slide_cluster":
        slide_key = "-".join(str(number) for number in affected_slide_numbers)
        return f"cluster:{group_id or slide_key}"
    return f"slide:{affected_slide_numbers[0]}"


def _change_summary(change: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "change_id": change.get("change_id"),
        "slide_number": change.get("slide_number"),
        "affected_slide_numbers": change.get("affected_slide_numbers")
        or [change.get("slide_number")],
        "packet_scope": change.get("packet_scope"),
        "execution_group_id": change.get("execution_group_id"),
        "dependency_change_ids": change.get("dependency_change_ids") or [],
        "requested_change": change.get("requested_change"),
        "execution_strategy": change.get("execution_strategy"),
    }


def _records_by_change_id(
    payload: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if payload is None:
        return {}
    records: dict[str, dict[str, Any]] = {}
    changes = payload.get("changes")
    if not isinstance(changes, list):
        return records
    for change in changes:
        if not isinstance(change, dict):
            continue
        change_id = str(change.get("change_id") or "").strip()
        if change_id:
            records[change_id] = dict(change)
    return records


def _packet_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        f"# Deck Revision Execution Packet {packet['packet_id']}",
        "",
        f"Scope: `{packet['packet_scope']}`",
        f"Slides: `{packet['affected_slide_numbers']}`",
        f"Changes: `{packet['change_ids']}`",
        "",
        "Use this packet as the focused input for PPTX editing. Do not apply",
        "changes outside this packet unless the dependency notes explicitly require it.",
        "",
        "## Slides",
        "",
    ]
    for slide in packet["slides"]:
        lines.append(f"- Slide {slide['slide_number']}: {slide.get('title') or ''}")
    lines.extend(["", "## Changes", ""])
    for change in packet["changes"]:
        lines.extend(
            [
                f"### {change['change_id']}",
                "",
                f"- Requested change: {change['requested_change']}",
                f"- Interpretation: {change['interpretation']}",
                f"- Strategy: `{change['execution_strategy']}`",
                f"- Confidence: `{change['confidence']}` / `{change['explicitness']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Guardrails",
            "",
            "- Treat this packet as the execution unit.",
            "- Use related-change summaries only for coherence, not as permission to edit them.",
            "- Verify this packet's success criteria before moving on.",
            "",
        ]
    )
    return "\n".join(lines)


def _index_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Execution Packets",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        "These packets prevent a single huge deck-editing prompt. Clara/Codex should",
        "execute one packet at a time, not one deck-editing prompt for the whole plan,",
        "then run packet-level and full-deck review.",
        "",
        f"- Packet count: {payload['summary']['packet_count']}",
        f"- Deck packets: {payload['summary']['deck_packets']}",
        f"- Slide-cluster packets: {payload['summary']['slide_cluster_packets']}",
        f"- Slide packets: {payload['summary']['slide_packets']}",
        "",
        "## Packets",
        "",
    ]
    for packet in payload["packets"]:
        lines.append(
            f"- `{packet['packet_id']}` `{packet['packet_scope']}` slides "
            f"`{packet['affected_slide_numbers']}` changes `{packet['change_ids']}`: "
            f"`{packet['packet_path']}`"
        )
    lines.append("")
    return "\n".join(lines)


def build_deck_revision_execution_packets(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    plan_path: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionExecutionPacketsResult:
    """Build slide/cluster/deck execution packets from a normalized plan.

    This deterministic step is justified because it only groups already
    model-authored change records by explicit scope, strategy, group id, and
    affected slides. It does not infer the semantic meaning of a requested edit.
    """

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    resolved_plan_path, plan = _load_plan(session_dir, plan_path, case_dir)
    workbench = _required_workbench(session_dir)
    slides = _slide_records(workbench)
    slide_lookup = {slide["slide_number"]: slide for slide in slides}
    changes = plan.get("changes")
    if not isinstance(changes, list):
        raise CaseWorkspaceError("normalized deck revision plan has no changes list")

    execution_payload = _read_optional_json(
        session_dir / "deck_revision_execution_plan.json"
    )
    material_payload = _read_optional_json(
        session_dir / "deck_revision_material_needs.json"
    )
    execution_by_change = _records_by_change_id(execution_payload)
    material_by_change = _records_by_change_id(material_payload)
    quote_matrix_path = session_dir / "deck_revision_quote_candidate_matrix.json"
    quote_matrix_review_path = session_dir / "deck_revision_quote_candidate_matrix.md"

    packet_groups: dict[str, dict[str, Any]] = {}
    ordered_group_keys: list[str] = []
    normalized_changes: list[dict[str, Any]] = [
        dict(change) for change in changes if isinstance(change, dict)
    ]
    for index, change in enumerate(normalized_changes, start=1):
        affected = _affected_slide_numbers(change, slide_lookup)
        scope = _packet_scope(change, affected)
        key = _group_key(change, scope, affected)
        if key not in packet_groups:
            ordered_group_keys.append(key)
            packet_groups[key] = {
                "packet_scope": scope,
                "first_change_index": index,
                "affected_slide_numbers": [],
                "changes": [],
            }
        group = packet_groups[key]
        group["changes"].append(change)
        for number in affected:
            if number not in group["affected_slide_numbers"]:
                group["affected_slide_numbers"].append(number)

    packet_dir = session_dir / "deck_revision_execution_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    created_at = _now_iso(now)
    deck_outline = _deck_outline(slides)
    all_change_summaries = [_change_summary(change) for change in normalized_changes]
    packets: list[dict[str, Any]] = []

    for packet_number, key in enumerate(ordered_group_keys, start=1):
        group = packet_groups[key]
        packet_id = f"packet-{packet_number:03d}"
        affected = sorted(group["affected_slide_numbers"])
        packet_changes = group["changes"]
        packet_change_ids = [change["change_id"] for change in packet_changes]
        packet_path = packet_dir / f"{packet_id}.json"
        review_path = packet_dir / f"{packet_id}.md"
        packet = {
            "schema_version": 1,
            "source": "clara_deck_revision_execution_packet",
            "created_at": created_at,
            "packet_id": packet_id,
            "packet_scope": group["packet_scope"],
            "execution_order": packet_number,
            "group_key": key,
            "change_ids": packet_change_ids,
            "affected_slide_numbers": affected,
            "global_context": {
                "workbench_path": _relative_path(
                    case_dir, session_dir / "deck_revision_workbench.json"
                ),
                "normalized_plan_path": _relative_path(case_dir, resolved_plan_path),
                "execution_plan_path": (
                    _relative_path(
                        case_dir, session_dir / "deck_revision_execution_plan.json"
                    )
                    if execution_payload is not None
                    else None
                ),
                "material_needs_path": (
                    _relative_path(
                        case_dir, session_dir / "deck_revision_material_needs.json"
                    )
                    if material_payload is not None
                    else None
                ),
                "quote_candidate_matrix_path": (
                    _relative_path(case_dir, quote_matrix_path)
                    if quote_matrix_path.is_file()
                    else None
                ),
                "quote_candidate_matrix_review_path": (
                    _relative_path(case_dir, quote_matrix_review_path)
                    if quote_matrix_review_path.is_file()
                    else None
                ),
                "deck_path": workbench["source_paths"]["deck_path"],
                "deck_snapshot_path": workbench["source_paths"]["deck_snapshot_path"],
                "deck_style_spec_path": workbench["source_paths"][
                    "deck_style_spec_path"
                ],
                "attributed_transcript_path": workbench["source_paths"][
                    "attributed_transcript_path"
                ],
            },
            "deck_outline": deck_outline,
            "slides": [slide_lookup[number] for number in affected],
            "changes": packet_changes,
            "execution_status": [
                execution_by_change[change_id]
                for change_id in packet_change_ids
                if change_id in execution_by_change
            ],
            "material_needs": [
                material_by_change[change_id]
                for change_id in packet_change_ids
                if change_id in material_by_change
            ],
            "related_change_summaries": [
                summary
                for summary in all_change_summaries
                if summary.get("change_id") not in packet_change_ids
            ],
            "dependency_change_ids": sorted(
                {
                    dependency
                    for change in packet_changes
                    for dependency in _text_list(change.get("dependency_change_ids"))
                }
            ),
            "execution_guardrails": [
                "Execute only this packet before moving to the next packet.",
                "Use related-change summaries only to preserve coherence.",
                "If a deck-level packet changes slide order or count, refresh slide references before local slide packets.",
                "Verify the packet success criteria, then run the full-deck output review loop.",
            ],
            "deterministic_boundary": (
                "Packet creation groups approved change records for focused execution; "
                "it does not decide what the partner meant."
            ),
        }
        _write_json(packet_path, packet)
        review_path.write_text(_packet_markdown(packet), encoding="utf-8")
        packets.append(
            {
                "packet_id": packet_id,
                "packet_scope": group["packet_scope"],
                "execution_order": packet_number,
                "change_ids": packet_change_ids,
                "affected_slide_numbers": affected,
                "packet_path": _relative_path(case_dir, packet_path),
                "review_path": _relative_path(case_dir, review_path),
            }
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_execution_packets",
        "created_at": created_at,
        "voice_session": _relative_path(case_dir, session_dir),
        "normalized_plan_path": _relative_path(case_dir, resolved_plan_path),
        "summary": {
            "status": "ready_for_packet_execution" if packets else "no_changes",
            "packet_count": len(packets),
            "change_count": len(normalized_changes),
            "deck_packets": sum(
                1 for packet in packets if packet["packet_scope"] == "deck"
            ),
            "slide_cluster_packets": sum(
                1 for packet in packets if packet["packet_scope"] == "slide_cluster"
            ),
            "slide_packets": sum(
                1 for packet in packets if packet["packet_scope"] == "slide"
            ),
        },
        "deterministic_boundary": (
            "Packets are deterministic packaging around model-authored changes; "
            "semantic understanding remains Clara/Codex work."
        ),
        "packets": packets,
    }
    index_path = session_dir / "deck_revision_execution_packets.json"
    review_path = session_dir / "deck_revision_execution_packets.md"
    _write_json(index_path, payload)
    review_path.write_text(_index_markdown(payload), encoding="utf-8")
    return DeckRevisionExecutionPacketsResult(
        session_dir=session_dir,
        packet_index_path=index_path,
        review_path=review_path,
        packet_dir=packet_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build focused Clara deck-revision execution packets.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--voice-session",
        type=Path,
        default=None,
        help="Voice session folder name/path. Defaults to latest voice session.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Normalized change plan. Defaults to deck_revision_changes.normalized.json.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_deck_revision_execution_packets(
        args.case_dir,
        voice_session=args.voice_session,
        plan_path=args.plan,
    )
    LOGGER.info("wrote execution packets to %s", result.packet_index_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
