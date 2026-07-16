"""Apply a reviewed transcript integration plan to a Clara case workspace."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from advisor_case_core import (
    CaseWorkspaceError,
    add_judgement_entries,
    refresh_case_brief,
    upsert_case_issues,
    validate_case_workspace,
)

__all__ = ["integrate_transcript_review", "main"]

LOGGER = logging.getLogger(__name__)

CASE_FILES = {
    "manifest": "case_manifest.json",
    "materials": "material_registry.json",
    "judgement": "judgement_log.json",
    "open_questions": "open_questions.json",
    "issues": "case_issues.json",
}


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseWorkspaceError(f"{path.name}: JSON payload must be an object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _case_file(case_dir: Path, key: str) -> Path:
    return case_dir / CASE_FILES[key]


def _list_from_plan(plan: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = plan.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise CaseWorkspaceError(f"{key} must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise CaseWorkspaceError(f"{key} items must be objects")
    return value


def _case_owned_path(case_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (case_dir / path).resolve()
    try:
        resolved.relative_to(case_dir.resolve())
    except ValueError as exc:
        raise CaseWorkspaceError(
            f"review note path must be inside case workspace: {raw_path}"
        ) from exc
    return resolved


def _touch_manifest(case_dir: Path, timestamp: str) -> None:
    manifest_path = _case_file(case_dir, "manifest")
    manifest = _read_json(manifest_path)
    manifest["updated_at"] = timestamp
    _write_json(manifest_path, manifest)


def _merge_metadata(
    material: dict[str, Any],
    metadata_update: Mapping[str, Any] | None,
) -> None:
    if not metadata_update:
        return
    existing = material.get("source_metadata")
    if existing is None:
        material["source_metadata"] = {}
        existing = material["source_metadata"]
    if not isinstance(existing, dict):
        raise CaseWorkspaceError("source_metadata must be an object before merging")
    for key, value in metadata_update.items():
        existing[str(key)] = value


def _update_material_registry(
    case_dir: Path,
    updates: Sequence[Mapping[str, Any]],
    *,
    timestamp: str,
) -> list[str]:
    if not updates:
        return []

    registry_path = _case_file(case_dir, "materials")
    registry = _read_json(registry_path)
    materials = registry.get("materials")
    if not isinstance(materials, list):
        raise CaseWorkspaceError("material_registry.json: materials must be a list")
    by_id = {str(item.get("id")): item for item in materials if isinstance(item, dict)}
    updated_ids: list[str] = []

    for update in updates:
        material_id = str(update.get("material_id", "")).strip()
        if not material_id:
            raise CaseWorkspaceError("material registry updates require material_id")
        material = by_id.get(material_id)
        if material is None:
            raise CaseWorkspaceError(f"unknown material_id: {material_id}")

        raw_path = update.get("path")
        if raw_path is not None:
            candidate = Path(str(raw_path)).expanduser()
            new_path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (case_dir / candidate).resolve()
            )
            if not new_path.exists():
                raise FileNotFoundError(new_path)
            material["path"] = str(new_path)

        for field in ("title", "summary", "status", "last_reviewed"):
            if field in update:
                material[field] = update[field]
        metadata_update = update.get("source_metadata")
        if metadata_update is not None and not isinstance(metadata_update, dict):
            raise CaseWorkspaceError("source_metadata update must be an object")
        _merge_metadata(material, metadata_update)
        material["updated_at"] = timestamp
        updated_ids.append(material_id)

    _write_json(registry_path, registry)
    return updated_ids


def _replace_review_section(text: str, heading: str, body: str) -> str:
    marker = f"## {heading}\n\n"
    start = text.find(marker)
    if start < 0:
        raise CaseWorkspaceError(f"review note section not found: {heading}")
    content_start = start + len(marker)
    next_heading = text.find("\n## ", content_start)
    if next_heading < 0:
        return text[:content_start] + body.strip() + "\n"
    return text[:content_start] + body.strip() + "\n\n" + text[next_heading + 1 :]


def _update_review_notes(
    case_dir: Path,
    updates: Sequence[Mapping[str, Any]],
) -> list[str]:
    updated_paths: list[str] = []
    for update in updates:
        raw_path = str(update.get("path", "")).strip()
        if not raw_path:
            raise CaseWorkspaceError("review note updates require path")
        sections = update.get("sections")
        if not isinstance(sections, dict):
            raise CaseWorkspaceError("review note sections must be an object")
        path = _case_owned_path(case_dir, raw_path)
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        for heading, body in sections.items():
            text = _replace_review_section(text, str(heading), str(body))
        path.write_text(text, encoding="utf-8")
        updated_paths.append(str(path))
    return updated_paths


def _existing_judgement_ids_by_text(case_dir: Path) -> dict[str, str]:
    payload = _read_json(_case_file(case_dir, "judgement"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise CaseWorkspaceError("judgement_log.json: entries must be a list")
    return {
        str(entry.get("text", "")): str(entry.get("id"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("text") and entry.get("id")
    }


def _add_judgements(
    case_dir: Path,
    entries: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not entries:
        return {}, []

    existing_by_text = _existing_judgement_ids_by_text(case_dir)
    key_to_id: dict[str, str] = {}
    entries_to_add: list[Mapping[str, Any]] = []
    keys_to_add: list[str] = []

    for index, entry in enumerate(entries, start=1):
        text = str(entry.get("text", "")).strip()
        if not text:
            raise CaseWorkspaceError("judgement entries require text")
        key = str(entry.get("key") or f"entry_{index}").strip()
        if not key:
            raise CaseWorkspaceError("judgement key cannot be empty")
        if key in key_to_id:
            raise CaseWorkspaceError(f"duplicate judgement key: {key}")
        existing_id = existing_by_text.get(text)
        if existing_id:
            key_to_id[key] = existing_id
            continue
        entries_to_add.append(entry)
        keys_to_add.append(key)

    added = add_judgement_entries(case_dir, entries_to_add) if entries_to_add else []
    for key, entry in zip(keys_to_add, added, strict=True):
        key_to_id[key] = str(entry["id"])
    return key_to_id, added


def _known_judgement_ids(case_dir: Path) -> set[str]:
    payload = _read_json(_case_file(case_dir, "judgement"))
    return {
        str(entry.get("id"))
        for entry in payload.get("entries", [])
        if isinstance(entry, dict) and entry.get("id")
    }


def _resolve_entry_ref(
    ref: Any,
    key_to_id: Mapping[str, str],
    known_judgement_ids: set[str],
) -> str:
    value = str(ref).strip()
    if value in key_to_id:
        return key_to_id[value]
    if value in known_judgement_ids:
        return value
    raise CaseWorkspaceError(f"unknown judgement reference: {value}")


def _resolve_entry_refs(
    refs: Any,
    key_to_id: Mapping[str, str],
    known_judgement_ids: set[str],
) -> list[str]:
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise CaseWorkspaceError("judgement references must be a list")
    resolved: list[str] = []
    for ref in refs:
        entry_id = _resolve_entry_ref(ref, key_to_id, known_judgement_ids)
        if entry_id not in resolved:
            resolved.append(entry_id)
    return resolved


def _merge_ids(existing: Sequence[str], additions: Sequence[str]) -> list[str]:
    merged = [str(item) for item in existing]
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def _update_open_question_links(
    case_dir: Path,
    updates: Sequence[Mapping[str, Any]],
    *,
    key_to_id: Mapping[str, str],
    timestamp: str,
) -> list[dict[str, Any]]:
    if not updates:
        return []

    known_judgement_ids = _known_judgement_ids(case_dir)
    questions_path = _case_file(case_dir, "open_questions")
    payload = _read_json(questions_path)
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise CaseWorkspaceError("open_questions.json: questions must be a list")
    by_id = {str(item.get("id")): item for item in questions if isinstance(item, dict)}
    summary: list[dict[str, Any]] = []

    for update in updates:
        question_id = str(update.get("question_id", "")).strip()
        if not question_id:
            raise CaseWorkspaceError("question link updates require question_id")
        question = by_id.get(question_id)
        if question is None:
            raise CaseWorkspaceError(f"unknown question_id: {question_id}")
        additions = _resolve_entry_refs(
            update.get("source_entry_refs", update.get("source_entry_ids", [])),
            key_to_id,
            known_judgement_ids,
        )
        existing = question.get("source_entry_ids", [])
        if not isinstance(existing, list):
            raise CaseWorkspaceError("source_entry_ids must be a list")
        question["source_entry_ids"] = _merge_ids(existing, additions)
        question["updated_at"] = timestamp
        summary.append({"question_id": question_id, "source_entry_ids": additions})

    _write_json(questions_path, payload)
    return summary


def _update_case_issues(
    case_dir: Path,
    updates: Sequence[Mapping[str, Any]],
    *,
    key_to_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    if not updates:
        return []

    known_judgement_ids = _known_judgement_ids(case_dir)
    issues_payload = _read_json(_case_file(case_dir, "issues"))
    existing_by_id = {
        str(item.get("id")): item
        for item in issues_payload.get("issues", [])
        if isinstance(item, dict)
    }
    upserts: list[dict[str, Any]] = []

    for update in updates:
        issue_id = str(update.get("issue_id", update.get("id", ""))).strip()
        existing = existing_by_id.get(issue_id)
        if existing is None and not update.get("title"):
            raise CaseWorkspaceError("new case issue updates require title")
        evidence_for = _merge_ids(
            existing.get("evidence_for", []) if existing else [],
            _resolve_entry_refs(
                update.get("evidence_for_refs", update.get("evidence_for", [])),
                key_to_id,
                known_judgement_ids,
            ),
        )
        evidence_against = _merge_ids(
            existing.get("evidence_against", []) if existing else [],
            _resolve_entry_refs(
                update.get(
                    "evidence_against_refs",
                    update.get("evidence_against", []),
                ),
                key_to_id,
                known_judgement_ids,
            ),
        )
        open_tests = _merge_ids(
            existing.get("open_tests", []) if existing else [],
            [str(item).strip() for item in update.get("open_test_ids", [])],
        )
        upserts.append(
            {
                "id": issue_id,
                "title": update.get(
                    "title", existing.get("title", "") if existing else ""
                ),
                "decision_area": update.get(
                    "decision_area",
                    existing.get("decision_area", "") if existing else "",
                ),
                "current_synthesis": update.get(
                    "current_synthesis",
                    existing.get("current_synthesis", "") if existing else "",
                ),
                "evidence_for": evidence_for,
                "evidence_against": evidence_against,
                "open_tests": open_tests,
                "status": update.get(
                    "status", existing.get("status", "active") if existing else "active"
                ),
            }
        )

    updated = upsert_case_issues(case_dir, upserts)
    return [
        {
            "issue_id": item["id"],
            "evidence_for": item["evidence_for"],
            "evidence_against": item["evidence_against"],
        }
        for item in updated
    ]


def integrate_transcript_review(
    case_dir: Path,
    plan: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply a deterministic integration plan and return an evidence summary."""

    case_dir = case_dir.resolve()
    before_errors = validate_case_workspace(case_dir)
    if before_errors:
        raise CaseWorkspaceError(
            "workspace invalid before integration: " + "; ".join(before_errors)
        )

    timestamp = _now_iso(now)
    material_updates = _update_material_registry(
        case_dir,
        _list_from_plan(plan, "material_registry_updates"),
        timestamp=timestamp,
    )
    review_notes = _update_review_notes(case_dir, _list_from_plan(plan, "review_notes"))
    key_to_id, added_judgements = _add_judgements(
        case_dir,
        _list_from_plan(plan, "judgements"),
    )
    open_question_links = _update_open_question_links(
        case_dir,
        _list_from_plan(plan, "open_question_links"),
        key_to_id=key_to_id,
        timestamp=timestamp,
    )
    case_issue_links = _update_case_issues(
        case_dir,
        _list_from_plan(plan, "case_issue_updates"),
        key_to_id=key_to_id,
    )

    if material_updates or review_notes or open_question_links:
        _touch_manifest(case_dir, timestamp)
    refresh_case_brief(case_dir, now=now)

    after_errors = validate_case_workspace(case_dir)
    summary = {
        "updated_at": timestamp,
        "validation_errors": after_errors,
        "material_updates": material_updates,
        "review_notes": review_notes,
        "judgement_key_map": key_to_id,
        "added_judgement_ids": [item["id"] for item in added_judgements],
        "open_question_links": open_question_links,
        "case_issue_links": case_issue_links,
    }
    if after_errors:
        raise CaseWorkspaceError(
            "workspace invalid after integration: " + "; ".join(after_errors)
        )
    return summary


def _load_plan(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    allowed = {
        "material_registry_updates",
        "review_notes",
        "judgements",
        "open_question_links",
        "case_issue_updates",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CaseWorkspaceError("unknown integration plan keys: " + ", ".join(unknown))
    return payload


def main() -> int:
    """Run the transcript integration CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--plan-json", required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        summary = integrate_transcript_review(args.case_dir, _load_plan(args.plan_json))
    except (CaseWorkspaceError, FileNotFoundError, json.JSONDecodeError) as exc:
        LOGGER.error("Transcript integration failed: %s", exc)
        return 1

    LOGGER.info(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
