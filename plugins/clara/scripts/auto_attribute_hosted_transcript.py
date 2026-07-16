"""Create reviewable speaker attribution artifacts for hosted voice imports."""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from finalize_hosted_transcript import (
    FinalizeHostedTranscriptResult,
    finalize_hosted_transcript,
)

__all__ = [
    "AutoTranscriptAttributionResult",
    "auto_attribute_hosted_transcript",
    "main",
]

REPORT_FILENAME = "speaker_attribution_report.json"
ATTRIBUTED_TRANSCRIPT_FILENAME = "attributed_transcript.md"
ATTRIBUTION_TASK_FILENAME = "speaker_attribution_task.md"
LOGGER = logging.getLogger(__name__)
SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
SPEAKER_LINE_RE = re.compile(
    r"^\s*(?:\[[^\]\n]{1,40}\]\s*)?(?P<label>[^:\n]{2,80}):\s+\S",
    re.MULTILINE,
)
SPEAKER_SPLIT_RE = re.compile(r"\s*(?:;|\n|\||,|/|&|\band\b|\be\b)\s*", re.I)
ROLE_SEPARATOR_RE = re.compile(r"\s+(?:-|--|/|\(|:)\s+|\s+\(")


@dataclass(frozen=True)
class AutoTranscriptAttributionResult:
    """Files created by local transcript attribution intake."""

    status: str
    method: str
    report_path: Path
    attributed_transcript_path: Path | None
    attribution_task_path: Path | None
    finalized_transcript: FinalizeHostedTranscriptResult | None
    speaker_labels: tuple[str, ...]
    candidate_speaker_names: tuple[str, ...]
    requires_review: bool


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _relative_path(case_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(case_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_markdown_section(markdown: str, heading: str) -> str:
    lines = markdown.replace("\r\n", "\n").splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        match = SECTION_RE.match(line)
        if match is not None:
            title = match.group("title").strip().lower()
            if in_section:
                break
            in_section = title == heading.strip().lower()
            continue
        if in_section:
            collected.append(line)
    return "\n".join(collected).strip()


def _main_transcript_text(raw_markdown: str) -> str:
    consultant = _extract_markdown_section(raw_markdown, "Consultant")
    if consultant:
        return consultant
    return raw_markdown.strip()


def _clean_speaker_candidate(value: str) -> str:
    clean = _normalise_space(value.strip(" -*\t\r\n"))
    if not clean:
        return ""
    clean = ROLE_SEPARATOR_RE.split(clean, maxsplit=1)[0]
    clean = clean.rstrip(").").strip()
    return clean


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _normalise_space(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return tuple(result)


def _metadata_speaker_candidates(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw_values: list[str] = []
    for key in ("participants", "interviewer"):
        value = str(metadata.get(key, "")).strip()
        if value:
            raw_values.extend(SPEAKER_SPLIT_RE.split(value))
    return _dedupe(
        [
            candidate
            for candidate in (_clean_speaker_candidate(value) for value in raw_values)
            if candidate
        ]
    )


def _explicit_main_transcript_labels(main_text: str) -> tuple[str, ...]:
    return _dedupe(
        [
            _normalise_space(match.group("label").strip())
            for match in SPEAKER_LINE_RE.finditer(main_text)
        ]
    )


def _attributed_transcript_markdown(
    *,
    raw_transcript_path: Path,
    main_text: str,
    speaker_labels: Sequence[str],
    method: str,
    source_metadata: Mapping[str, Any],
    call_metadata: Mapping[str, Any],
) -> str:
    lines = [
        "# Speaker-Attributed Hosted Voice Transcript",
        "",
        f"Source raw transcript: {raw_transcript_path.name}",
        f"Attribution method: {method}",
        "",
        "## Attribution Inputs",
        "",
        "```json",
        json.dumps(
            {
                "source_metadata": dict(source_metadata),
                "call_metadata": dict(call_metadata),
            },
            indent=2,
            ensure_ascii=True,
        ),
        "```",
        "",
        "## Attributed Transcript",
        "",
    ]
    if method == "metadata_single_speaker":
        speaker = speaker_labels[0]
        lines.append(f"{speaker}: {_normalise_space(main_text)}")
    else:
        lines.append(main_text.strip())
    lines.append("")
    return "\n".join(lines)


def _attribution_task_markdown(
    *,
    raw_transcript_path: Path,
    main_text: str,
    candidate_speaker_names: Sequence[str],
    source_metadata: Mapping[str, Any],
    call_metadata: Mapping[str, Any],
    unresolved_notes: Sequence[str],
) -> str:
    candidates = (
        ", ".join(candidate_speaker_names)
        if candidate_speaker_names
        else "Not supplied"
    )
    return "\n".join(
        [
            "# Speaker Attribution Task",
            "",
            "This transcript needs Clara/Codex speaker attribution before deck-revision work can use it.",
            "",
            "## Required Output",
            "",
            f"- Write `{ATTRIBUTED_TRANSCRIPT_FILENAME}` in this voice-session folder.",
            "- Assign speaker turns from the transcript text and call metadata.",
            "- If real names are unknown, use stable labels such as `Speaker 1` and `Speaker 2`.",
            "- Preserve transcript order and substance; do not summarize.",
            "- Keep uncertainty visible instead of guessing.",
            "",
            "## Available Speaker Metadata",
            "",
            f"- Candidate speaker names: {candidates}",
            "",
            "## Attribution Inputs",
            "",
            "```json",
            json.dumps(
                {
                    "source_metadata": dict(source_metadata),
                    "call_metadata": dict(call_metadata),
                    "unresolved_notes": list(unresolved_notes),
                },
                indent=2,
                ensure_ascii=True,
            ),
            "```",
            "",
            "## Transcript To Attribute",
            "",
            f"Source raw transcript: `{raw_transcript_path.name}`",
            "",
            main_text.strip(),
            "",
        ]
    )


def _write_report(
    *,
    report_path: Path,
    case_dir: Path,
    raw_transcript_path: Path,
    attributed_transcript_path: Path | None,
    attribution_task_path: Path | None,
    status: str,
    method: str,
    speaker_labels: Sequence[str],
    candidate_speaker_names: Sequence[str],
    source_metadata: Mapping[str, Any],
    call_metadata: Mapping[str, Any],
    requires_review: bool,
    unresolved_notes: Sequence[str],
    now: datetime | None,
) -> None:
    payload = {
        "schema_version": 1,
        "source": "clara_auto_transcript_attribution",
        "created_at": _now_iso(now),
        "status": status,
        "method": method,
        "requires_review": requires_review,
        "speaker_labels": list(speaker_labels),
        "candidate_speaker_names": list(candidate_speaker_names),
        "speaker_labels_are_provisional": False,
        "requires_clara_codex_attribution": status != "attributed",
        "raw_transcript_path": _relative_path(case_dir, raw_transcript_path),
        "attributed_transcript_path": _relative_path(
            case_dir,
            attributed_transcript_path,
        ),
        "attribution_task_path": _relative_path(case_dir, attribution_task_path),
        "source_metadata": dict(source_metadata),
        "call_metadata": dict(call_metadata),
        "unresolved_notes": list(unresolved_notes),
    }
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _attribution_plan(
    *,
    main_text: str,
    source_metadata: Mapping[str, Any],
) -> tuple[str, str, tuple[str, ...], tuple[str, ...], bool, list[str]]:
    metadata_candidates = _metadata_speaker_candidates(source_metadata)
    explicit_labels = _explicit_main_transcript_labels(main_text)
    if len(metadata_candidates) == 1:
        return (
            "attributed",
            "metadata_single_speaker",
            metadata_candidates,
            metadata_candidates,
            False,
            [],
        )
    unresolved = [
        "Speaker attribution requires local Clara/Codex review from transcript text; "
        "deterministic code cannot assign turn boundaries safely.",
    ]
    if len(metadata_candidates) > 1:
        unresolved.append(
            "Multiple metadata speaker names were supplied; Clara/Codex must map "
            "transcript turns to the correct names.",
        )
    elif not metadata_candidates:
        unresolved.append(
            "No speaker names were supplied in call metadata; use Speaker labels "
            "until Clara/Codex can infer or the user supplies names."
        )
    if explicit_labels:
        unresolved.append(
            "The transcript text already contains speaker-like labels; Clara/Codex "
            "must verify or replace them before registering an attributed transcript."
        )
    return (
        "needs_model_attribution",
        "requires_clara_codex_attribution",
        (),
        metadata_candidates,
        True,
        unresolved,
    )


def auto_attribute_hosted_transcript(
    case_dir: Path,
    material_id: str,
    raw_transcript_path: Path,
    *,
    source_metadata: Mapping[str, Any] | None = None,
    call_metadata: Mapping[str, Any] | None = None,
    attributed_transcript_path: Path | None = None,
    attribution_task_path: Path | None = None,
    report_path: Path | None = None,
    now: datetime | None = None,
) -> AutoTranscriptAttributionResult:
    """Create safe local speaker attribution artifacts for a hosted transcript.

    Deterministic code only handles the safe shortcut: a single known speaker.
    Semantic multi-speaker attribution remains a local Clara/Codex task.
    """

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))
    raw_path = raw_transcript_path.expanduser()
    if not raw_path.is_file():
        raise CaseWorkspaceError(f"raw transcript does not exist: {raw_path}")
    session_dir = raw_path.parent
    attributed_path = (
        attributed_transcript_path.expanduser()
        if attributed_transcript_path is not None
        else session_dir / ATTRIBUTED_TRANSCRIPT_FILENAME
    )
    report = (
        report_path.expanduser()
        if report_path is not None
        else session_dir / REPORT_FILENAME
    )
    task_path = (
        attribution_task_path.expanduser()
        if attribution_task_path is not None
        else session_dir / ATTRIBUTION_TASK_FILENAME
    )

    raw_markdown = raw_path.read_text(encoding="utf-8")
    main_text = _main_transcript_text(raw_markdown)
    if not main_text:
        raise CaseWorkspaceError("raw transcript contains no transcript text")
    metadata = dict(source_metadata or {})
    call = dict(call_metadata or {})
    status, method, labels, candidates, requires_review, unresolved = _attribution_plan(
        main_text=main_text,
        source_metadata=metadata,
    )
    finalized: FinalizeHostedTranscriptResult | None = None
    attributed_path_out: Path | None = None
    task_path_out: Path | None = None
    if status == "attributed":
        attributed_path.write_text(
            _attributed_transcript_markdown(
                raw_transcript_path=raw_path,
                main_text=main_text,
                speaker_labels=labels,
                method=method,
                source_metadata=metadata,
                call_metadata=call,
            ),
            encoding="utf-8",
        )
        attributed_path_out = attributed_path
        note = (
            f"local Clara/Codex text attribution using {method}; "
            "no audio or voice diarization model used"
        )
        if method == "metadata_single_speaker":
            note = (
                "single-speaker local text attribution using metadata_single_speaker; "
                "no audio or voice diarization model used"
            )
        finalized = finalize_hosted_transcript(
            case_dir,
            material_id,
            attributed_path,
            raw_transcript_path=raw_path,
            speaker_attribution_note=note,
            now=now,
        )
    else:
        task_path.write_text(
            _attribution_task_markdown(
                raw_transcript_path=raw_path,
                main_text=main_text,
                candidate_speaker_names=candidates,
                source_metadata=metadata,
                call_metadata=call,
                unresolved_notes=unresolved,
            ),
            encoding="utf-8",
        )
        task_path_out = task_path

    _write_report(
        report_path=report,
        case_dir=case_dir,
        raw_transcript_path=raw_path,
        attributed_transcript_path=attributed_path_out,
        attribution_task_path=task_path_out,
        status=status,
        method=method,
        speaker_labels=labels,
        candidate_speaker_names=candidates,
        source_metadata=metadata,
        call_metadata=call,
        requires_review=requires_review,
        unresolved_notes=unresolved,
        now=now,
    )
    return AutoTranscriptAttributionResult(
        status=status,
        method=method,
        report_path=report,
        attributed_transcript_path=attributed_path_out,
        attribution_task_path=task_path_out,
        finalized_transcript=finalized,
        speaker_labels=labels,
        candidate_speaker_names=candidates,
        requires_review=requires_review,
    )


def main() -> int:
    """Run automatic hosted transcript attribution."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("material_id")
    parser.add_argument("raw_transcript", type=Path)
    parser.add_argument("--source-metadata-json", default="{}")
    parser.add_argument("--call-metadata-json", default="{}")
    args = parser.parse_args()
    try:
        source_metadata = json.loads(args.source_metadata_json)
        call_metadata = json.loads(args.call_metadata_json)
    except json.JSONDecodeError as error:
        raise CaseWorkspaceError("metadata arguments must be JSON objects") from error
    if not isinstance(source_metadata, dict) or not isinstance(call_metadata, dict):
        raise CaseWorkspaceError("metadata arguments must be JSON objects")
    result = auto_attribute_hosted_transcript(
        args.case_dir,
        args.material_id,
        args.raw_transcript,
        source_metadata=source_metadata,
        call_metadata=call_metadata,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    LOGGER.info("Speaker attribution report: %s", result.report_path)
    if result.attribution_task_path is not None:
        LOGGER.info("Speaker attribution task: %s", result.attribution_task_path)
    if result.attributed_transcript_path is not None:
        LOGGER.info("Attributed transcript: %s", result.attributed_transcript_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
